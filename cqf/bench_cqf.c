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
 *             <distribution_label> <output_csv> [default|invertible|none] [distinct_keys]
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
    if (strlen(path) >= 4 && strcmp(path + strlen(path) - 4, ".bin") == 0) {
        FILE *bf = fopen(path, "rb");
        if (!bf) { fprintf(stderr, "Could not open %s\n", path); exit(1); }
        if (fseek(bf, 0, SEEK_END) != 0) exit(1);
        long bytes = ftell(bf); rewind(bf);
        if (bytes < 0 || bytes % (long)sizeof(uint64_t)) exit(1);
        uint64_t count = (uint64_t)bytes / sizeof(uint64_t);
        uint64_t *arr = (uint64_t*)malloc((size_t)bytes);
        if (!arr || fread(arr, sizeof(uint64_t), count, bf) != count) exit(1);
        fclose(bf); *out = arr; return count;
    }
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

static uint64_t splitmix64(uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
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
    if (argc < 7 || argc > 10) {
        fprintf(stderr,
            "Usage: %s <positive_file> <negative_file> <qbits> <rbits> "
            "<distribution_label> <output_csv> [default|invertible|none] [distinct_keys] [skip-delete]\n", argv[0]);
        return 1;
    }
    const char *pos_file = argv[1];
    const char *neg_file = argv[2];
    uint64_t qbits = strtoull(argv[3], NULL, 10);
    uint64_t rbits = strtoull(argv[4], NULL, 10);
    const char *dist_label = argv[5];
    const char *out_csv = argv[6];
    const char *mode_name = argc >= 8 ? argv[7] : "default";
    uint64_t declared_distinct = argc >= 9 ? strtoull(argv[8], NULL, 10) : 0;
    int skip_delete = argc >= 10 && !strcmp(argv[9], "skip-delete");
    if (argc >= 10 && !skip_delete) {
        fprintf(stderr, "Optional final argument must be skip-delete\n");
        return 2;
    }
    enum qf_hashmode hash_mode;
    if (!strcmp(mode_name, "default")) hash_mode = QF_HASH_DEFAULT;
    else if (!strcmp(mode_name, "invertible")) hash_mode = QF_HASH_INVERTIBLE;
    else if (!strcmp(mode_name, "none")) hash_mode = QF_HASH_NONE;
    else { fprintf(stderr, "Unknown hash mode: %s\n", mode_name); return 2; }

    uint64_t nhashbits = qbits + rbits;
    uint64_t nslots = 1ULL << qbits;

    uint64_t *pos_keys, *neg_keys;
    uint64_t n_pos = read_keys(pos_file, &pos_keys);
    uint64_t n_neg = read_keys(neg_file, &neg_keys);

    fprintf(stderr, "[cqf] loaded %" PRIu64 " positive, %" PRIu64
                     " negative keys (qbits=%" PRIu64 " rbits=%" PRIu64 ", mode=%s)\n",
                     n_pos, n_neg, qbits, rbits, mode_name);

    /* QF_HASH_NONE means the caller supplies a key already in the CQF key
       domain. Apply the external SplitMix64 mapping inside each timed phase
       so its cost is included in end-to-end throughput, just as DEFAULT and
       INVERTIBLE include their internal hash costs in qf_* calls. */
    const uint64_t external_hash_mask = (1ULL << nhashbits) - 1;

    QF qf;
    if (!qf_malloc(&qf, nslots, nhashbits, 0, hash_mode, 0)) {
        fprintf(stderr, "Could not allocate CQF (nslots=%" PRIu64 ")\n", nslots);
        return 1;
    }
    fprintf(stderr, "[cqf] table allocation complete (slots=%" PRIu64 ")\n", nslots);
    qf_set_auto_resize(&qf, false); /* keep capacity fixed for a fair, apples-to-apples run */

    /* ---- insert ---- */
    double t0 = now_sec();
    uint64_t n_inserted = 0;
    for (uint64_t i = 0; i < n_pos; i++) {
        uint64_t key = hash_mode == QF_HASH_NONE
                           ? (splitmix64(pos_keys[i]) & external_hash_mask)
                           : pos_keys[i];
        int ret = qf_insert(&qf, key, 0, 1, QF_NO_LOCK);
        if (ret < 0) {
            fprintf(stderr, "[cqf] filter full after %" PRIu64 " inserts (code %d), stopping insert phase\n", n_inserted, ret);
            break;
        }
        n_inserted++;
        if ((n_inserted % 10000000ULL) == 0) fprintf(stderr, "[cqf] inserted %" PRIu64 "/%" PRIu64 "\n", n_inserted, n_pos);
    }
    double insert_time = now_sec() - t0;
    fprintf(stderr, "[cqf] insert phase complete: %.2f Mops/s\n",
            n_inserted / (insert_time > 0 ? insert_time : 1e-9) / 1e6);

    /* ---- positive lookups ---- */
    t0 = now_sec();
    uint64_t found_pos = 0;
    for (uint64_t i = 0; i < n_inserted; i++) {
        uint64_t key = hash_mode == QF_HASH_NONE
                           ? (splitmix64(pos_keys[i]) & external_hash_mask)
                           : pos_keys[i];
        if (qf_count_key_value(&qf, key, 0, 0) > 0) found_pos++;
        if (((i + 1) % 10000000ULL) == 0) fprintf(stderr, "[cqf] positive lookups %" PRIu64 "/%" PRIu64 "\n", i + 1, n_inserted);
    }
    double query_pos_time = now_sec() - t0;
    fprintf(stderr, "[cqf] positive lookup phase complete: %.2f Mops/s\n",
            found_pos / (query_pos_time > 0 ? query_pos_time : 1e-9) / 1e6);

    /* ---- negative lookups (false-positive measurement) ---- */
    t0 = now_sec();
    uint64_t false_positives = 0;
    for (uint64_t i = 0; i < n_neg; i++) {
        uint64_t key = hash_mode == QF_HASH_NONE
                           ? (splitmix64(neg_keys[i]) & external_hash_mask)
                           : neg_keys[i];
        if (qf_count_key_value(&qf, key, 0, 0) > 0) false_positives++;
    }
    double query_neg_time = now_sec() - t0;
    fprintf(stderr, "[cqf] negative lookup phase complete: %.2f Mops/s\n",
            n_neg / (query_neg_time > 0 ? query_neg_time : 1e-9) / 1e6);

    double measured_fp = (double)false_positives / (double)n_neg;
    /* Workload-specific expected collision probability over the CQF's
       2^(qbits+rbits) fingerprint domain, for all three hash modes. At a
       95% table load this is close to 0.95*2^-rbits; under a highly
       duplicated workload it falls with the number of distinct keys.
       The generator supplies its exact distinct count so a large CQF need
       not be scanned just to estimate FPR. */
    uint64_t n_distinct = declared_distinct ? declared_distinct
                                             : qf_get_num_distinct_key_value_pairs(&qf);
    double theoretical_fp = fmin(1.0, (double)n_distinct / pow(2.0, (double)nhashbits));

    /* ---- delete / decrement one occurrence per input item ---- */
    /* Large-scale hash-mode runs can omit deletion to isolate the hash path
       without spending most of the run in the CQF's expensive high-scale
       one-at-a-time deletion path. Deletion remains measured in the 1M hash
       study and in the filter-comparison benchmark. */
    double delete_time = 0.0;
    uint64_t deleted_ok = 0;
    if (!skip_delete) {
        /*
         * qf_delete_key_value() removes the entire counter for a key in one call.
         * Using it once per Zipfian input would therefore turn most later calls
         * into no-ops after the first occurrence and would wildly overstate delete
         * throughput. Measure one DELETE operation per inserted occurrence.
         */
        t0 = now_sec();
        for (uint64_t i = 0; i < n_inserted; i++) {
            uint64_t key = hash_mode == QF_HASH_NONE
                               ? (splitmix64(pos_keys[i]) & external_hash_mask)
                               : pos_keys[i];
            int ret = qf_remove(&qf, key, 0, 1, QF_NO_LOCK);
            if (ret >= 0) deleted_ok++;
            if ((i + 1) % 5000000ULL == 0) {
                fprintf(stderr, "[cqf] delete progress: %" PRIu64 "/%" PRIu64 " occurrences\n", i + 1, n_inserted);
            }
        }
        delete_time = now_sec() - t0;
        fprintf(stderr, "[cqf] delete phase complete: %.2f Mops/s\n",
                deleted_ok / (delete_time > 0 ? delete_time : 1e-9) / 1e6);

        /* Confirm all represented keys were removed. */
        uint64_t remaining_after_delete = 0;
        for (uint64_t i = 0; i < n_inserted; i++) {
            uint64_t key = hash_mode == QF_HASH_NONE
                               ? (splitmix64(pos_keys[i]) & external_hash_mask)
                               : pos_keys[i];
            if (qf_count_key_value(&qf, key, 0, 0) != 0) {
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
    } else {
        fprintf(stderr, "[cqf] deletion skipped by experiment design\n");
    }

    uint64_t mem_bytes = qf_get_total_size_in_bytes(&qf);

    char config_param[96];
    snprintf(config_param, sizeof(config_param), "qbits=%" PRIu64 ";rbits=%" PRIu64 ";hash=%s%s", qbits, rbits, mode_name, skip_delete ? ";delete=NA" : "");

    write_csv_header_if_needed(out_csv);
    FILE *csv = fopen(out_csv, "a");
    if (skip_delete) {
        fprintf(csv,
            "cqf,%s,%" PRIu64 ",%" PRIu64 ",%s,%" PRIu64 ","
            "%.6f,%.2f,%.6f,%.2f,%" PRIu64 ","
            "%.6f,%.2f,%.12g,%.12g,%.8g,NA,NA,NA\n",
            dist_label, n_pos, n_inserted, config_param, mem_bytes,
            insert_time, n_inserted / (insert_time > 0 ? insert_time : 1e-9),
            query_pos_time, n_inserted / (query_pos_time > 0 ? query_pos_time : 1e-9), found_pos,
            query_neg_time, n_neg / (query_neg_time > 0 ? query_neg_time : 1e-9),
            measured_fp, theoretical_fp, (theoretical_fp > 0 ? measured_fp / theoretical_fp : 0.0));
    } else {
        fprintf(csv,
            "cqf,%s,%" PRIu64 ",%" PRIu64 ",%s,%" PRIu64 ","
            "%.6f,%.2f,%.6f,%.2f,%" PRIu64 ","
            "%.6f,%.2f,%.12g,%.12g,%.8g,%.6f,%.2f,%" PRIu64 "\n",
            dist_label, n_pos, n_inserted, config_param, mem_bytes,
            insert_time, n_inserted / (insert_time > 0 ? insert_time : 1e-9),
            query_pos_time, n_inserted / (query_pos_time > 0 ? query_pos_time : 1e-9), found_pos,
            query_neg_time, n_neg / (query_neg_time > 0 ? query_neg_time : 1e-9),
            measured_fp, theoretical_fp, (theoretical_fp > 0 ? measured_fp / theoretical_fp : 0.0),
            delete_time, n_inserted / (delete_time > 0 ? delete_time : 1e-9), deleted_ok);
    }
    fclose(csv);

    if (skip_delete) {
        fprintf(stderr, "[cqf] done: inserted=%" PRIu64 " found_pos=%" PRIu64
                         " measured_fp=%.9g theoretical_fp=%.9g delete=N/A\n",
                         n_inserted, found_pos, measured_fp, theoretical_fp);
    } else {
        fprintf(stderr, "[cqf] done: inserted=%" PRIu64 " found_pos=%" PRIu64
                         " measured_fp=%.9g theoretical_fp=%.9g deleted_ok=%" PRIu64 "\n",
                         n_inserted, found_pos, measured_fp, theoretical_fp, deleted_ok);
    }

    qf_free(&qf);
    free(pos_keys);
    free(neg_keys);
    return 0;
}
