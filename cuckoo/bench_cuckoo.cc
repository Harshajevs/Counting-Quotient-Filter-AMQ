/*
 * bench_cuckoo.cc — unified benchmark driver for the cuckoo filter.
 *
 * Same CSV schema as bench_cqf.c and bench_bloom.cc, so all three filters
 * land in one comparison table (see ../scripts/plot_results.py).
 *
 * Usage:
 *   bench_cuckoo <positive_file> <negative_file> <capacity> <bits_per_item> \
 *                <distribution_label> <output_csv>
 *
 *   bits_per_item is the cuckoo filter's fingerprint size in bits (must be
 *   one of 8, 12, 16 — the sizes this driver supports, since it's a
 *   compile-time template parameter in the underlying library).
 *
 * Theoretical false-positive rate follows the cuckoo filter paper's own
 * formula: fp ~= 2 * b / 2^bits_per_item, where b = bucket associativity
 * (this implementation hardcodes b = 4 internally).
 */

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#include "src/cuckoofilter.h"

using namespace cuckoofilter;
using Clock = std::chrono::high_resolution_clock;

static double elapsed_sec(Clock::time_point t0, Clock::time_point t1) {
    return std::chrono::duration<double>(t1 - t0).count();
}

static std::vector<uint64_t> read_keys(const std::string &path) {
    std::ifstream in(path);
    if (!in) {
        fprintf(stderr, "Could not open %s\n", path.c_str());
        exit(1);
    }
    std::vector<uint64_t> out;
    out.reserve(1 << 16);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        out.push_back(strtoull(line.c_str(), nullptr, 10));
    }
    return out;
}

static void write_csv_header_if_needed(const std::string &path) {
    std::ifstream test(path);
    if (test.good()) return;
    std::ofstream f(path);
    f << "filter,distribution,n_requested,n_inserted,config_param,"
         "memory_bytes,insert_time_s,insert_ops_sec,"
         "query_pos_time_s,query_pos_ops_sec,found_positive,"
         "query_neg_time_s,query_neg_ops_sec,measured_fp_rate,"
         "theoretical_fp_rate,fp_ratio,delete_time_s,delete_ops_sec,deleted_ok\n";
}

template <size_t BITS>
static void run_bench(const std::vector<uint64_t> &pos, const std::vector<uint64_t> &neg,
                       size_t capacity, const std::string &dist_label, const std::string &out_csv) {
    CuckooFilter<uint64_t, BITS> filter(capacity);

    /* ---- insert ---- */
    auto t0 = Clock::now();
    size_t n_inserted = 0;
    for (size_t i = 0; i < pos.size(); i++) {
        if (filter.Add(pos[i]) != Ok) {
            fprintf(stderr, "[cuckoo] filter full/failed after %zu inserts, stopping insert phase\n", n_inserted);
            break;
        }
        n_inserted++;
    }
    double insert_time = elapsed_sec(t0, Clock::now());

    /* ---- positive lookups ---- */
    t0 = Clock::now();
    size_t found_pos = 0;
    for (size_t i = 0; i < n_inserted; i++) {
        if (filter.Contain(pos[i]) == Ok) found_pos++;
    }
    double query_pos_time = elapsed_sec(t0, Clock::now());

    /* ---- negative lookups (false-positive measurement) ---- */
    t0 = Clock::now();
    size_t false_positives = 0;
    for (size_t i = 0; i < neg.size(); i++) {
        if (filter.Contain(neg[i]) == Ok) false_positives++;
    }
    double query_neg_time = elapsed_sec(t0, Clock::now());

    double measured_fp = neg.empty() ? 0.0 : (double)false_positives / (double)neg.size();
    double theoretical_fp = 8.0 / (double)(1ULL << BITS); /* 2*assoc(=4) / 2^bits */

    /* ---- delete ---- */
    t0 = Clock::now();
    size_t deleted_ok = 0;
    for (size_t i = 0; i < n_inserted; i++) {
        if (filter.Delete(pos[i]) == Ok) deleted_ok++;
    }
    double delete_time = elapsed_sec(t0, Clock::now());

    size_t mem_bytes = filter.SizeInBytes();

    char config_param[64];
    snprintf(config_param, sizeof(config_param), "bits_per_item=%zu;assoc=4", BITS);

    write_csv_header_if_needed(out_csv);
    FILE *csv = fopen(out_csv.c_str(), "a");
    fprintf(csv,
        "cuckoo,%s,%zu,%zu,%s,%zu,"
        "%.6f,%.2f,"
        "%.6f,%.2f,%zu,"
        "%.6f,%.2f,%.8f,%.8f,%.4f,"
        "%.6f,%.2f,%zu\n",
        dist_label.c_str(), pos.size(), n_inserted, config_param, mem_bytes,
        insert_time, n_inserted / (insert_time > 0 ? insert_time : 1e-9),
        query_pos_time, n_inserted / (query_pos_time > 0 ? query_pos_time : 1e-9), found_pos,
        query_neg_time, neg.size() / (query_neg_time > 0 ? query_neg_time : 1e-9),
        measured_fp, theoretical_fp, (theoretical_fp > 0 ? measured_fp / theoretical_fp : 0.0),
        delete_time, n_inserted / (delete_time > 0 ? delete_time : 1e-9), deleted_ok);
    fclose(csv);

    fprintf(stderr, "[cuckoo] done: inserted=%zu found_pos=%zu measured_fp=%.6f theoretical_fp=%.6f deleted_ok=%zu\n",
            n_inserted, found_pos, measured_fp, theoretical_fp, deleted_ok);
}

int main(int argc, char **argv) {
    if (argc < 7) {
        fprintf(stderr,
            "Usage: %s <positive_file> <negative_file> <capacity> <bits_per_item(8|12|16)> "
            "<distribution_label> <output_csv>\n", argv[0]);
        return 1;
    }
    std::string pos_file = argv[1];
    std::string neg_file = argv[2];
    size_t capacity = strtoull(argv[3], nullptr, 10);
    int bits = atoi(argv[4]);
    std::string dist_label = argv[5];
    std::string out_csv = argv[6];

    auto pos = read_keys(pos_file);
    auto neg = read_keys(neg_file);
    fprintf(stderr, "[cuckoo] loaded %zu positive, %zu negative keys (capacity=%zu bits_per_item=%d)\n",
            pos.size(), neg.size(), capacity, bits);

    switch (bits) {
        case 8:  run_bench<8>(pos, neg, capacity, dist_label, out_csv);  break;
        case 12: run_bench<12>(pos, neg, capacity, dist_label, out_csv); break;
        case 16: run_bench<16>(pos, neg, capacity, dist_label, out_csv); break;
        default:
            fprintf(stderr, "bits_per_item must be 8, 12, or 16\n");
            return 1;
    }
    return 0;
}
