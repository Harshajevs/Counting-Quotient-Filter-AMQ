/*
 * bench_cqf.c — unified benchmark driver for the Counting Quotient Filter.
 *
 * Reads a positive-key file (keys to insert) and a negative-key file (keys
 * guaranteed not to be inserted, used to measure the false-positive rate),
 * runs insert / positive-lookup / negative-lookup / delete phases with
 * separate timing, and appends one CSV row with the results.
 *
 * This produces the SAME CSV schema as bench_cuckoo.cc and bench_bloom.cc
 * (see ../scripts/plot_results.py) so all three filters land in one table.
 *
 * Usage:
 *   bench_cqf <positive_file> <negative_file> <qbits> <rbits> \
 *             <distribution_label> <output_csv>
 *
 *   qbits  = log2(number of slots)   e.g. 22  ->  4,194,304 slots
 *   rbits  = remainder bits          e.g. 9   ->  theoretical FP = 2^-9
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <math.h>
#include <time.h>
#include <errno.h>

#include "include/gqf.h"
#include "include/gqf_int.h"

static double now_sec(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC_RAW, &ts) != 0) {
        perror("clock_gettime");
        exit(EXIT_FAILURE);
    }
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

/* Reads whitespace/newline separated uint64 decimal values from `path`.
 * Returns a malloc'd array via *out and the count via return value. */
static uint64_t read_keys(const char *path, uint64_t **out) {
    FILE *f = fopen(path, "r");
    if (!f) {
        fprintf(stderr, "Could not open %s\n", path);
        exit(1);
    }
    size_t cap = 1 << 16;
    uint64_t *arr = malloc(cap * sizeof(uint64_t));
    uint64_t n = 0;
    char line[64];
    while (fgets(line, sizeof(line), f)) {
        char *end;
        uint64_t v = strtoull(line, &end, 10);
        if (end == line) continue;
        if (n >= cap) {
            cap *= 2;
            arr = realloc(arr, cap * sizeof(uint64_t));
        }
        arr[n++] = v;
    }
    fclose(f);
    *out = arr;
    return n;
}

static void write_csv_header_if_needed(const char *path) {
    FILE *f = fopen(path, "r");
    if (f) { fclose(f); return; } /* already exists */
    f = fopen(path, "w");
    fprintf(f,
        "filter,distribution,n_requested,n_inserted,config_param,"
        "memory_bytes,insert_time_s,insert_ops_sec,"
        "query_pos_time_s,query_pos_ops_sec,found_positive,"
        "query_neg_time_s,query_neg_ops_sec,measured_fp_rate,"
        "theoretical_fp_rate,fp_ratio,delete_time_s,delete_ops_sec,deleted_ok\n");
    fclose(f);
}

int main(int argc, char **argv) {
    if (argc < 7) {
        fprintf(stderr,
            "Usage: %s <positive_file> <negative_file> <qbits> <rbits> "
            "<distribution_label> <output_csv>\n", argv[0]);
        return 1;
    }
    const char *pos_file = argv[1];
    const char *neg_file = argv[2];
    uint64_t qbits = strtoull(argv[3], NULL, 10);
    uint64_t rbits = strtoull(argv[4], NULL, 10);
    const char *dist_label = argv[5];
    const char *out_csv = argv[6];

    uint64_t nhashbits = qbits + rbits;
    uint64_t nslots = 1ULL << qbits;

    uint64_t *pos_keys, *neg_keys;
    uint64_t n_pos = read_keys(pos_file, &pos_keys);
    uint64_t n_neg = read_keys(neg_file, &neg_keys);

    fprintf(stderr, "[cqf] loaded %" PRIu64 " positive, %" PRIu64
                     " negative keys (qbits=%" PRIu64 " rbits=%" PRIu64 ")\n",
                     n_pos, n_neg, qbits, rbits);

    QF qf;
    if (!qf_malloc(&qf, nslots, nhashbits, 0, QF_HASH_DEFAULT, 0)) {
        fprintf(stderr, "Could not allocate CQF (nslots=%" PRIu64 ")\n", nslots);
        return 1;
    }
    qf_set_auto_resize(&qf, false); /* keep capacity fixed for a fair, apples-to-apples run */

    /* ---- insert ---- */
    double t0 = now_sec();
    uint64_t n_inserted = 0;
    for (uint64_t i = 0; i < n_pos; i++) {
        int ret = qf_insert(&qf, pos_keys[i], 0, 1, QF_NO_LOCK);
        if (ret < 0) {
            fprintf(stderr, "[cqf] filter full after %" PRIu64 " inserts (code %d), stopping insert phase\n", n_inserted, ret);
            break;
        }
        n_inserted++;
    }
    double insert_time = now_sec() - t0;

    /* ---- positive lookups ---- */
    t0 = now_sec();
    uint64_t found_pos = 0;
    for (uint64_t i = 0; i < n_inserted; i++) {
        if (qf_count_key_value(&qf, pos_keys[i], 0, 0) > 0) found_pos++;
    }
    double query_pos_time = now_sec() - t0;

    /* ---- negative lookups (false-positive measurement) ---- */
    t0 = now_sec();
    uint64_t false_positives = 0;
    for (uint64_t i = 0; i < n_neg; i++) {
        if (qf_count_key_value(&qf, neg_keys[i], 0, 0) > 0) false_positives++;
    }
    double query_neg_time = now_sec() - t0;

    double measured_fp = (double)false_positives / (double)n_neg;
    double theoretical_fp = pow(2.0, -(double)rbits);

    /* ---- delete / decrement one occurrence per input item ---- */
    /*
     * qf_delete_key_value() removes the entire counter for a key in one call.
     * Using it once per Zipfian input would therefore turn most later calls
     * into no-ops after the first occurrence and would wildly overstate delete
     * throughput.  The benchmark measures one DELETE operation per inserted
     * occurrence instead, so repeated keys exercise the CQF counter path.
     */
    t0 = now_sec();
    uint64_t deleted_ok = 0;
    for (uint64_t i = 0; i < n_inserted; i++) {
        int ret = qf_remove(&qf, pos_keys[i], 0, 1, QF_NO_LOCK);
        if (ret >= 0) deleted_ok++;
    }
    double delete_time = now_sec() - t0;

    /* After removing one occurrence for every insertion, every represented
     * key should have count zero.  This is a cheap functional check and is
     * deliberately outside the timed delete section. */
    uint64_t remaining_after_delete = 0;
    for (uint64_t i = 0; i < n_inserted; i++) {
        if (qf_count_key_value(&qf, pos_keys[i], 0, 0) != 0) {
            remaining_after_delete++;
            break;
        }
    }
    if (remaining_after_delete != 0 || deleted_ok != n_inserted) {
        fprintf(stderr, "[cqf] deletion validation FAILED: deleted_ok=%" PRIu64
                        " expected=%" PRIu64 " remaining=%" PRIu64 "\n",
                deleted_ok, n_inserted, remaining_after_delete);
        qf_free(&qf);
        free(pos_keys);
        free(neg_keys);
        return EXIT_FAILURE;
    }

    uint64_t mem_bytes = qf_get_total_size_in_bytes(&qf);

    char config_param[64];
    snprintf(config_param, sizeof(config_param), "qbits=%" PRIu64 ";rbits=%" PRIu64, qbits, rbits);

    write_csv_header_if_needed(out_csv);
    FILE *csv = fopen(out_csv, "a");
    fprintf(csv,
        "cqf,%s,%" PRIu64 ",%" PRIu64 ",%s,%" PRIu64 ","
        "%.6f,%.2f,"
        "%.6f,%.2f,%" PRIu64 ","
        "%.6f,%.2f,%.8f,%.8f,%.4f,"
        "%.6f,%.2f,%" PRIu64 "\n",
        dist_label, n_pos, n_inserted, config_param, mem_bytes,
        insert_time, n_inserted / (insert_time > 0 ? insert_time : 1e-9),
        query_pos_time, n_inserted / (query_pos_time > 0 ? query_pos_time : 1e-9), found_pos,
        query_neg_time, n_neg / (query_neg_time > 0 ? query_neg_time : 1e-9),
        measured_fp, theoretical_fp, (theoretical_fp > 0 ? measured_fp / theoretical_fp : 0.0),
        delete_time, n_inserted / (delete_time > 0 ? delete_time : 1e-9), deleted_ok);
    fclose(csv);

    fprintf(stderr, "[cqf] done: inserted=%" PRIu64 " found_pos=%" PRIu64
                     " measured_fp=%.6f theoretical_fp=%.6f deleted_ok=%" PRIu64 "\n",
                     n_inserted, found_pos, measured_fp, theoretical_fp, deleted_ok);

    qf_free(&qf);
    free(pos_keys);
    free(neg_keys);
    return 0;
}
