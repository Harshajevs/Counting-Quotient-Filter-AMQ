/*
 * bench_bloom.cc — unified benchmark driver for the reference Bloom filter
 * (bloom_filter.hpp, a minimal 4-hash-function bit-array implementation).
 *
 * Same CSV schema as bench_cqf.c and bench_cuckoo.cc, so all three filters
 * land in one comparison table (see ../scripts/plot_results.py).
 *
 * NOTE: bloom_filter.hpp has no Delete() — Bloom filters fundamentally
 * can't support deletion without extra structure (e.g. counters), which is
 * exactly one of the gaps the CQF paper points out. The delete columns in
 * this driver's CSV row are filled with 0 to make that limitation explicit
 * and keep the schema aligned across all three filters, rather than
 * silently omitting the columns.
 *
 * Usage:
 *   bench_bloom <positive_file> <negative_file> <size_bits> <num_hashes> \
 *               <distribution_label> <output_csv>
 */

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

#include "bloom_filter.hpp"

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

int main(int argc, char **argv) {
    if (argc < 7) {
        fprintf(stderr,
            "Usage: %s <positive_file> <negative_file> <size_bits> <num_hashes> "
            "<distribution_label> <output_csv>\n", argv[0]);
        return 1;
    }
    std::string pos_file = argv[1];
    std::string neg_file = argv[2];
    size_t size_bits = strtoull(argv[3], nullptr, 10);
    size_t num_hashes = strtoull(argv[4], nullptr, 10);
    std::string dist_label = argv[5];
    std::string out_csv = argv[6];

    /* this implementation uses exactly 4 hash functions regardless of
     * num_hashes (see bloom_filter.hpp) — we still accept and record the
     * parameter for transparency in the CSV / future extension */
    (void)num_hashes;

    auto pos = read_keys(pos_file);
    auto neg = read_keys(neg_file);
    fprintf(stderr, "[bloom] loaded %zu positive, %zu negative keys (size_bits=%zu)\n",
            pos.size(), neg.size(), size_bits);

    BloomFilter filter(size_bits, 4);

    /* ---- insert ---- */
    auto t0 = Clock::now();
    for (size_t i = 0; i < pos.size(); i++) {
        filter.insert(std::to_string(pos[i]));
    }
    double insert_time = elapsed_sec(t0, Clock::now());
    size_t n_inserted = pos.size(); /* Bloom filters never "reject" an insert */

    /* ---- positive lookups ---- */
    t0 = Clock::now();
    size_t found_pos = 0;
    for (size_t i = 0; i < pos.size(); i++) {
        if (filter.contains(std::to_string(pos[i]))) found_pos++;
    }
    double query_pos_time = elapsed_sec(t0, Clock::now());

    /* ---- negative lookups (false-positive measurement) ---- */
    t0 = Clock::now();
    size_t false_positives = 0;
    for (size_t i = 0; i < neg.size(); i++) {
        if (filter.contains(std::to_string(neg[i]))) false_positives++;
    }
    double query_neg_time = elapsed_sec(t0, Clock::now());

    double measured_fp = neg.empty() ? 0.0 : (double)false_positives / (double)neg.size();

    /* Standard Bloom filter theoretical FP formula: (1 - e^(-k*n/m))^k
     * k = num hash functions (fixed at 4 in this implementation)
     * n = number of inserted items, m = filter size in bits */
    double k = 4.0;
    double m = (double)size_bits;
    double n = (double)n_inserted;
    double theoretical_fp = pow(1.0 - exp(-k * n / m), k);

    size_t mem_bytes = size_bits / 8;

    char config_param[64];
    snprintf(config_param, sizeof(config_param), "size_bits=%zu;k=4", size_bits);

    write_csv_header_if_needed(out_csv);
    FILE *csv = fopen(out_csv.c_str(), "a");
    fprintf(csv,
        "bloom,%s,%zu,%zu,%s,%zu,"
        "%.6f,%.2f,"
        "%.6f,%.2f,%zu,"
        "%.6f,%.2f,%.8f,%.8f,%.4f,"
        "%.6f,%.2f,%zu\n",
        dist_label.c_str(), pos.size(), n_inserted, config_param, mem_bytes,
        insert_time, n_inserted / (insert_time > 0 ? insert_time : 1e-9),
        query_pos_time, n_inserted / (query_pos_time > 0 ? query_pos_time : 1e-9), found_pos,
        query_neg_time, neg.size() / (query_neg_time > 0 ? query_neg_time : 1e-9),
        measured_fp, theoretical_fp, (theoretical_fp > 0 ? measured_fp / theoretical_fp : 0.0),
        /* delete not supported by this Bloom filter -- see file header comment */
        0.0, 0.0, (size_t)0);
    fclose(csv);

    fprintf(stderr, "[bloom] done: inserted=%zu found_pos=%zu measured_fp=%.6f theoretical_fp=%.6f (delete not supported)\n",
            n_inserted, found_pos, measured_fp, theoretical_fp);
    return 0;
}
