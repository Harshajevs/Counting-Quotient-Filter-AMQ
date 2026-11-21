#include "amq_extra.hpp"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>

using Clock = std::chrono::steady_clock;
static double seconds(Clock::time_point a, Clock::time_point b) {
    return std::chrono::duration<double>(b-a).count();
}

static std::vector<uint64_t> read_bin(const std::string &path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    if (!in) throw std::runtime_error("cannot open input: " + path);
    std::streamoff bytes = in.tellg();
    if (bytes < 0 || bytes % static_cast<std::streamoff>(sizeof(uint64_t)) != 0)
        throw std::runtime_error("input is not a uint64 binary file: " + path);
    std::vector<uint64_t> values(static_cast<size_t>(bytes / sizeof(uint64_t)));
    in.seekg(0);
    if (!values.empty()) in.read(reinterpret_cast<char*>(values.data()), bytes);
    if (!in && !values.empty()) throw std::runtime_error("short read: " + path);
    return values;
}

static void ensure_header(const std::string &path) {
    std::ifstream test(path);
    if (test.good()) return;
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create CSV: " + path);
    out << "filter,filter_class,operation_model,distribution,repeat_id,n_requested,n_distinct,n_inserted,config_param,memory_bytes,preprocess_time_s,build_time_s,build_ops_sec,insert_supported,insert_time_s,insert_ops_sec,query_pos_count,query_pos_time_s,query_pos_ops_sec,found_positive,query_neg_count,query_neg_time_s,query_neg_ops_sec,false_positives,measured_fp_rate,theoretical_fp_rate,fp_ratio,delete_supported,delete_time_s,delete_ops_sec,deleted_ok,auxiliary_bytes\n";
}

static std::string na() { return "NA"; }
static void emit_row(const std::string &path, const std::string &filter,
                     const std::string &filter_class, const std::string &operation_model,
                     const std::string &dist, int repeat_id, size_t n_requested,
                     size_t n_distinct, size_t n_inserted, const std::string &config,
                     uint64_t memory_bytes, double preprocess_s,
                     const std::string &build_time, const std::string &build_rate,
                     bool insert_supported, const std::string &insert_time,
                     const std::string &insert_rate, size_t query_count,
                     double pos_time, size_t found, size_t neg_count,
                     double neg_time, size_t fps, double measured_fp,
                     double theoretical_fp, bool delete_supported,
                     const std::string &delete_time, const std::string &delete_rate,
                     const std::string &deleted_ok, uint64_t auxiliary_bytes=0) {
    ensure_header(path);
    std::ofstream out(path, std::ios::app);
    if (!out) throw std::runtime_error("cannot append CSV: " + path);
    double pos_rate = query_count / std::max(pos_time, 1e-12);
    double neg_rate = neg_count / std::max(neg_time, 1e-12);
    double ratio = theoretical_fp > 0 ? measured_fp / theoretical_fp : 0;
    out << filter << ',' << filter_class << ',' << operation_model << ',' << dist << ',' << repeat_id << ','
        << n_requested << ',' << n_distinct << ',' << n_inserted << ',' << '"' << config << '"' << ','
        << memory_bytes << ',' << std::fixed << std::setprecision(9) << preprocess_s << ','
        << build_time << ',' << build_rate << ',' << (insert_supported ? "yes" : "no") << ','
        << insert_time << ',' << insert_rate << ',' << query_count << ',' << pos_time << ','
        << std::fixed << std::setprecision(2) << pos_rate << ',' << found << ',' << neg_count << ','
        << std::fixed << std::setprecision(9) << neg_time << ',' << std::fixed << std::setprecision(2) << neg_rate << ','
        << fps << ',' << std::scientific << std::setprecision(12) << measured_fp << ','
        << theoretical_fp << ',' << ratio << ',' << (delete_supported ? "yes" : "no") << ','
        << delete_time << ',' << delete_rate << ',' << deleted_ok << ',' << auxiliary_bytes << '\n';
}

static void run_counting_bloom(const std::vector<uint64_t> &pos,
                               const std::vector<uint64_t> &neg, size_t distinct,
                               double target, const std::string &dist, int rep,
                               const std::string &csv) {
    amqextra::CountingBloomFilter filter(distinct, target);
    auto t0=Clock::now();
    for(uint64_t k:pos) filter.insert(k);
    double insert_s=seconds(t0,Clock::now());

    t0=Clock::now(); size_t found=0;
    for(uint64_t k:pos) if(filter.contains(k)) ++found;
    double qpos_s=seconds(t0,Clock::now());

    t0=Clock::now(); size_t fp=0;
    for(uint64_t k:neg) if(filter.contains(k)) ++fp;
    double qneg_s=seconds(t0,Clock::now());

    const uint64_t memory_before_delete = filter.memory_bytes();
    const size_t overflow_peak = filter.overflow_cells();
    t0=Clock::now(); size_t deleted=0;
    for(uint64_t k:pos) if(filter.erase(k)) ++deleted;
    double delete_s=seconds(t0,Clock::now());

    unsigned kh=filter.hashes();
    double p=std::pow(1.0-std::exp(-static_cast<double>(kh)*distinct/filter.cells()),static_cast<double>(kh));
    std::ostringstream cfg; cfg << "4bit_counters;cells=" << filter.cells() << ";k=" << kh
                                << ";overflow_cells_peak=" << overflow_peak;
    emit_row(csv,"counting_bloom","dynamic","online_insert_delete",dist,rep,pos.size(),distinct,pos.size(),cfg.str(),
             memory_before_delete,0,na(),na(),true,std::to_string(insert_s),
             std::to_string(pos.size()/std::max(insert_s,1e-12)),pos.size(),qpos_s,found,neg.size(),qneg_s,fp,
             static_cast<double>(fp)/std::max<size_t>(1,neg.size()),p,true,std::to_string(delete_s),
             std::to_string(pos.size()/std::max(delete_s,1e-12)),std::to_string(deleted));
    if(found!=pos.size() || deleted!=pos.size()) throw std::runtime_error("Counting Bloom correctness check failed");
}

static void run_blocked_bloom(const std::vector<uint64_t> &pos,
                              const std::vector<uint64_t> &neg, size_t distinct,
                              double target, const std::string &dist, int rep,
                              const std::string &csv) {
    amqextra::BlockedBloomFilter filter(distinct,target);
    auto t0=Clock::now();
    for(uint64_t k:pos) filter.insert(k);
    double insert_s=seconds(t0,Clock::now());
    t0=Clock::now(); size_t found=0;
    for(uint64_t k:pos) if(filter.contains(k)) ++found;
    double qpos_s=seconds(t0,Clock::now());
    t0=Clock::now(); size_t fp=0;
    for(uint64_t k:neg) if(filter.contains(k)) ++fp;
    double qneg_s=seconds(t0,Clock::now());
    std::ostringstream cfg; cfg << "block_bits=512;blocks=" << filter.blocks() << ";k=" << filter.hashes();
    emit_row(csv,"blocked_bloom","dynamic","online_insert_no_delete",dist,rep,pos.size(),distinct,pos.size(),cfg.str(),
             filter.memory_bytes(),0,na(),na(),true,std::to_string(insert_s),
             std::to_string(pos.size()/std::max(insert_s,1e-12)),pos.size(),qpos_s,found,neg.size(),qneg_s,fp,
             static_cast<double>(fp)/std::max<size_t>(1,neg.size()),filter.theoretical_fpr(distinct),false,
             na(),na(),na());
    if(found!=pos.size()) throw std::runtime_error("Blocked Bloom positive lookup check failed");
}

template<class Filter>
static void run_static_filter(const char *name, Filter &filter,
                              const std::vector<uint64_t> &unique_keys,
                              const std::vector<uint64_t> &pos,
                              const std::vector<uint64_t> &neg,
                              size_t distinct, unsigned fp_bits,
                              double preprocess_s, const std::string &dist,
                              int rep, const std::string &csv) {
    auto t0=Clock::now();
    if(!filter.build(unique_keys,fp_bits)) throw std::runtime_error(std::string(name)+" construction failed after retries");
    double build_s=seconds(t0,Clock::now());

    t0=Clock::now(); size_t found=0;
    for(uint64_t k:pos) if(filter.contains(k)) ++found;
    double qpos_s=seconds(t0,Clock::now());
    t0=Clock::now(); size_t fp=0;
    for(uint64_t k:neg) if(filter.contains(k)) ++fp;
    double qneg_s=seconds(t0,Clock::now());
    double theory=std::ldexp(1.0,-static_cast<int>(fp_bits));
    std::ostringstream cfg; cfg << "static;fingerprint_bits=" << fp_bits << ";distinct_keys=" << distinct;
    emit_row(csv,name,"static","immutable_build_query",dist,rep,pos.size(),distinct,distinct,cfg.str(),
             filter.memory_bytes(),preprocess_s,std::to_string(build_s),
             std::to_string(distinct/std::max(build_s,1e-12)),false,na(),na(),pos.size(),qpos_s,found,
             neg.size(),qneg_s,fp,static_cast<double>(fp)/std::max<size_t>(1,neg.size()),theory,
             false,na(),na(),na());
    if(found!=pos.size()) throw std::runtime_error(std::string(name)+" positive lookup check failed");
}

int main(int argc,char **argv) {
    if(argc!=7) {
        std::cerr << "Usage: " << argv[0] << " <positive.bin> <negative.bin> <target_fpr> <distribution> <raw.csv> <repeat_id>\n";
        return 2;
    }
    try {
        const std::string pos_path=argv[1],neg_path=argv[2],dist=argv[4],csv=argv[5];
        const double target=std::strtod(argv[3],nullptr);
        const int rep=std::atoi(argv[6]);
        if(!(target>0.0 && target<1.0)) throw std::invalid_argument("target FPR must be in (0,1)");
        std::cerr << "[extra] loading shared binary workloads...\n";
        std::vector<uint64_t> pos=read_bin(pos_path), neg=read_bin(neg_path);
        if(pos.empty()||neg.empty()) throw std::runtime_error("positive and negative files must be non-empty");
        std::cerr << "[extra] operations=" << pos.size() << " negatives=" << neg.size() << "\n";

        auto prep0=Clock::now();
        std::vector<uint64_t> unique_keys=pos;
        if(dist!="uniform") {
            std::sort(unique_keys.begin(),unique_keys.end());
            unique_keys.erase(std::unique(unique_keys.begin(),unique_keys.end()),unique_keys.end());
        }
        double prep_s=seconds(prep0,Clock::now());
        const size_t distinct=unique_keys.size();
        const unsigned fp_bits=amqextra::fingerprint_bits(target);
        std::cerr << "[extra] distinct=" << distinct << " fingerprint_bits=" << fp_bits << "\n";

        run_blocked_bloom(pos,neg,distinct,target,dist,rep,csv);
        run_counting_bloom(pos,neg,distinct,target,dist,rep,csv);

        amqextra::XorFilter xor_filter;
        run_static_filter("xor",xor_filter,unique_keys,pos,neg,distinct,fp_bits,prep_s,dist,rep,csv);

        amqextra::BinaryFuseFilter fuse_filter;
        // One guard bit beyond ceil(-log2(target)) gives the scalar reference
        // margin below the requested FPR after independently hashing the
        // fingerprint from the position hash.
        run_static_filter("binary_fuse",fuse_filter,unique_keys,pos,neg,distinct,fp_bits+1,prep_s,dist,rep,csv);

        std::cerr << "[extra] all four added filters passed positive lookup checks\n";
    } catch(const std::exception &e) {
        std::cerr << "[extra] ERROR: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
