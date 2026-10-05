/*
 * bench_bloom.cc — unified benchmark driver for the Bloom filter.
 *
 * The driver uses raw uint64_t keys so timed sections contain only the filter
 * operation itself.  This is important for a fair comparison with the C/C++
 * CQF and cuckoo implementations and is closer to the paper's benchmark,
 * which feeds pre-generated 64-bit values to the filters.
 *
 * Usage:
 *   bench_bloom <positive_file> <negative_file> <size_bits> <num_hashes> \
 *               <distribution_label> <output_csv>
 */

#include <chrono>
#include <cmath>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

#include "bloom_filter.hpp"

using Clock = std::chrono::steady_clock;

static double elapsed_sec(Clock::time_point t0, Clock::time_point t1) {
    return std::chrono::duration<double>(t1 - t0).count();
}

static std::vector<std::uint64_t> read_keys(const std::string &path) {
    std::ifstream in(path);
    if (!in) {
        std::fprintf(stderr, "[bloom] could not open %s\n", path.c_str());
        std::exit(EXIT_FAILURE);
    }

    std::vector<std::uint64_t> out;
    out.reserve(1U << 20);
    std::uint64_t value;
    while (in >> value) out.push_back(value);
    return out;
}

static void write_csv_header_if_needed(const std::string &path) {
    std::ifstream test(path);
    if (test.good()) return;

    std::ofstream out(path);
    if (!out) {
        std::fprintf(stderr, "[bloom] could not create %s\n", path.c_str());
        std::exit(EXIT_FAILURE);
    }
    out << "filter,distribution,n_requested,n_inserted,config_param,"
           "memory_bytes,insert_time_s,insert_ops_sec,"
           "query_pos_time_s,query_pos_ops_sec,found_positive,"
           "query_neg_time_s,query_neg_ops_sec,measured_fp_rate,"
           "theoretical_fp_rate,fp_ratio,delete_time_s,delete_ops_sec,deleted_ok\n";
}

int main(int argc, char **argv) {
    if (argc < 7) {
        std::fprintf(stderr,
            "Usage: %s <positive_file> <negative_file> <size_bits> <num_hashes> "
            "<distribution_label> <output_csv>\n", argv[0]);
        return EXIT_FAILURE;
    }

    const std::string pos_file = argv[1];
    const std::string neg_file = argv[2];
    const std::size_t size_bits = static_cast<std::size_t>(std::strtoull(argv[3], nullptr, 10));
    const std::size_t num_hashes = static_cast<std::size_t>(std::strtoull(argv[4], nullptr, 10));
    const std::string dist_label = argv[5];
    const std::string out_csv = argv[6];

    if (size_bits == 0 || num_hashes == 0) {
        std::fprintf(stderr, "[bloom] size_bits and num_hashes must be positive\n");
        return EXIT_FAILURE;
    }

    const auto pos = read_keys(pos_file);
    const auto neg = read_keys(neg_file);
    std::fprintf(stderr,
                 "[bloom] loaded %zu positive, %zu negative keys (size_bits=%zu k=%zu)\n",
                 pos.size(), neg.size(), size_bits, num_hashes);

    BloomFilter filter(size_bits, num_hashes);
    const std::size_t n_inserted = pos.size();

    // ---- insert ----
    auto t0 = Clock::now();
    for (std::uint64_t key : pos) filter.insert(key);
    const double insert_time = elapsed_sec(t0, Clock::now());

    // ---- positive lookups ----
    t0 = Clock::now();
    std::size_t found_pos = 0;
    for (std::uint64_t key : pos) {
        if (filter.contains(key)) ++found_pos;
    }
    const double query_pos_time = elapsed_sec(t0, Clock::now());

    // ---- negative lookups / measured false positives ----
    t0 = Clock::now();
    std::size_t false_positives = 0;
    for (std::uint64_t key : neg) {
        if (filter.contains(key)) ++false_positives;
    }
    const double query_neg_time = elapsed_sec(t0, Clock::now());

    const double measured_fp = neg.empty()
        ? 0.0
        : static_cast<double>(false_positives) / static_cast<double>(neg.size());

    // Standard Bloom-filter FPR approximation for n inserted operations and m bits.
    // For the Zipfian workload this is intentionally conservative because many
    // insertions are duplicates; duplicates do not set additional bits.
    const double k = static_cast<double>(num_hashes);
    const double m = static_cast<double>(size_bits);
    const double n = static_cast<double>(n_inserted);
    const double theoretical_fp = std::pow(1.0 - std::exp(-k * n / m), k);

    char config_param[96];
    std::snprintf(config_param, sizeof(config_param),
                  "size_bits=%zu;k=%zu", size_bits, num_hashes);

    write_csv_header_if_needed(out_csv);
    FILE *csv = std::fopen(out_csv.c_str(), "a");
    if (!csv) {
        std::fprintf(stderr, "[bloom] could not open %s for append\n", out_csv.c_str());
        return EXIT_FAILURE;
    }

    const double insert_ops = n_inserted / (insert_time > 0.0 ? insert_time : 1e-12);
    const double pos_ops = n_inserted / (query_pos_time > 0.0 ? query_pos_time : 1e-12);
    const double neg_ops = neg.size() / (query_neg_time > 0.0 ? query_neg_time : 1e-12);
    const double fp_ratio = theoretical_fp > 0.0 ? measured_fp / theoretical_fp : 0.0;

    std::fprintf(csv,
        "bloom,%s,%zu,%zu,%s,%zu,"
        "%.9f,%.2f,"
        "%.9f,%.2f,%zu,"
        "%.9f,%.2f,%.8f,%.8f,%.4f,"
        "0.000000000,0.00,0\n",
        dist_label.c_str(), pos.size(), n_inserted, config_param, filter.size_in_bytes(),
        insert_time, insert_ops,
        query_pos_time, pos_ops, found_pos,
        query_neg_time, neg_ops, measured_fp, theoretical_fp, fp_ratio);
    std::fclose(csv);

    std::fprintf(stderr,
                 "[bloom] done: inserted=%zu found_pos=%zu false_positives=%zu "
                 "measured_fp=%.6f theoretical_fp=%.6f\n",
                 n_inserted, found_pos, false_positives, measured_fp, theoretical_fp);
    return EXIT_SUCCESS;
}
