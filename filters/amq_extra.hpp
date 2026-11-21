#ifndef AMQ_EXTRA_FILTERS_HPP
#define AMQ_EXTRA_FILTERS_HPP

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace amqextra {

static inline uint64_t mix64(uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

static inline uint64_t rotl64(uint64_t x, unsigned r) {
    return (x << r) | (x >> (64 - r));
}

static inline uint64_t reduce64(uint64_t h, uint64_t n) {
    return static_cast<uint64_t>((static_cast<__uint128_t>(h) * n) >> 64);
}

static inline unsigned fingerprint_bits(double target_fpr) {
    if (!(target_fpr > 0.0 && target_fpr < 1.0))
        throw std::invalid_argument("target FPR must be in (0,1)");
    return static_cast<unsigned>(std::ceil(-std::log2(target_fpr)));
}

static inline uint64_t bloom_cells(uint64_t n, double p, unsigned &k) {
    if (n == 0) n = 1;
    const double ln2 = std::log(2.0);
    double bpe = -std::log(p) / (ln2 * ln2);
    k = std::max(1u, static_cast<unsigned>(std::llround(bpe * ln2)));
    return static_cast<uint64_t>(std::ceil(-static_cast<double>(k) * n /
        std::log(1.0 - std::pow(p, 1.0 / static_cast<double>(k)))));
}

static inline std::pair<uint64_t,uint64_t> bloom_hashes(uint64_t key, uint64_t seed) {
    uint64_t h1 = mix64(key ^ seed);
    uint64_t h2 = mix64(key ^ (seed + 0x9e3779b97f4a7c15ULL)) | 1ULL;
    return {h1,h2};
}

class CountingBloomFilter {
public:
    explicit CountingBloomFilter(uint64_t expected_items, double target_fpr, uint64_t seed=0x243f6a8885a308d3ULL)
        : seed_(seed) {
        cells_ = bloom_cells(expected_items, target_fpr, k_);
        // Four-bit counters, with an exact overflow side table for hot cells.
        counters_.assign(static_cast<size_t>((cells_ + 1) / 2), 0);
    }

    void insert(uint64_t key) {
        auto h = bloom_hashes(key, seed_);
        for (unsigned i=0; i<k_; ++i) {
            uint64_t idx = (h.first + static_cast<uint64_t>(i) * h.second) % cells_;
            uint8_t c = get_nibble(idx);
            if (c < 15) set_nibble(idx, static_cast<uint8_t>(c+1));
            else {
                auto it = overflow_.find(idx);
                if (it == overflow_.end()) overflow_.emplace(idx, 16);
                else ++it->second;
            }
        }
    }

    bool contains(uint64_t key) const {
        auto h = bloom_hashes(key, seed_);
        for (unsigned i=0; i<k_; ++i) {
            uint64_t idx = (h.first + static_cast<uint64_t>(i) * h.second) % cells_;
            if (get_count(idx) == 0) return false;
        }
        return true;
    }

    bool erase(uint64_t key) {
        auto h = bloom_hashes(key, seed_);
        uint64_t idxs[32];
        if (k_ > 32) return false;
        for (unsigned i=0; i<k_; ++i) {
            idxs[i] = (h.first + static_cast<uint64_t>(i) * h.second) % cells_;
            if (get_count(idxs[i]) == 0) return false;
        }
        for (unsigned i=0; i<k_; ++i) {
            uint64_t idx = idxs[i];
            uint8_t c = get_nibble(idx);
            if (c == 15) {
                auto it = overflow_.find(idx);
                if (it != overflow_.end()) {
                    if (it->second > 16) --it->second;
                    else { overflow_.erase(it); set_nibble(idx, 15); }
                } else if (c > 0) set_nibble(idx, static_cast<uint8_t>(c-1));
            } else if (c > 0) set_nibble(idx, static_cast<uint8_t>(c-1));
        }
        return true;
    }

    uint64_t cells() const { return cells_; }
    unsigned hashes() const { return k_; }
    uint64_t memory_bytes() const {
        // Approximate actual dynamic allocation, including a conservative
        // node/bucket allowance for the overflow map.
        return counters_.size() + overflow_.size() * 48ULL + overflow_.bucket_count() * sizeof(void*);
    }
    size_t overflow_cells() const { return overflow_.size(); }

private:
    uint8_t get_nibble(uint64_t idx) const {
        uint8_t b = counters_[static_cast<size_t>(idx >> 1)];
        return (idx & 1ULL) ? static_cast<uint8_t>(b >> 4) : static_cast<uint8_t>(b & 0x0f);
    }
    void set_nibble(uint64_t idx, uint8_t value) {
        uint8_t &b = counters_[static_cast<size_t>(idx >> 1)];
        if (idx & 1ULL) b = static_cast<uint8_t>((b & 0x0f) | (value << 4));
        else b = static_cast<uint8_t>((b & 0xf0) | (value & 0x0f));
    }
    uint64_t get_count(uint64_t idx) const {
        uint8_t c = get_nibble(idx);
        if (c != 15) return c;
        auto it = overflow_.find(idx);
        return it == overflow_.end() ? 15 : it->second;
    }

    uint64_t cells_=0, seed_=0;
    unsigned k_=0;
    std::vector<uint8_t> counters_;
    std::unordered_map<uint64_t,uint64_t> overflow_;
};

class BlockedBloomFilter {
public:
    static constexpr uint64_t BLOCK_BITS = 512;
    explicit BlockedBloomFilter(uint64_t expected_items, double target_fpr, uint64_t seed=0x13198a2e03707344ULL)
        : seed_(seed) {
        uint64_t ideal_bits = bloom_cells(expected_items, target_fpr, k_);
        // Block-level occupancy is overdispersed relative to a conventional
        // Bloom array. A 20% guard keeps the measured rate near the requested
        // target across workloads while retaining cache-line locality.
        uint64_t guarded_bits = static_cast<uint64_t>(std::ceil(1.20 * ideal_bits));
        blocks_ = std::max<uint64_t>(1, (guarded_bits + BLOCK_BITS - 1) / BLOCK_BITS);
        bits_.assign(static_cast<size_t>(blocks_ * (BLOCK_BITS/8)), 0);
    }
    void insert(uint64_t key) {
        uint64_t hblock = mix64(key ^ seed_);
        uint64_t block = reduce64(hblock, blocks_);
        uint8_t *base = bits_.data() + static_cast<size_t>(block * (BLOCK_BITS/8));
        for (unsigned i=0; i<k_; ++i) {
            uint64_t bit = mix64(key ^ (seed_ + 0x9e3779b97f4a7c15ULL * (i+1))) & (BLOCK_BITS-1);
            base[bit >> 3] |= static_cast<uint8_t>(1U << (bit & 7));
        }
    }
    bool contains(uint64_t key) const {
        uint64_t hblock = mix64(key ^ seed_);
        uint64_t block = reduce64(hblock, blocks_);
        const uint8_t *base = bits_.data() + static_cast<size_t>(block * (BLOCK_BITS/8));
        for (unsigned i=0; i<k_; ++i) {
            uint64_t bit = mix64(key ^ (seed_ + 0x9e3779b97f4a7c15ULL * (i+1))) & (BLOCK_BITS-1);
            if ((base[bit >> 3] & static_cast<uint8_t>(1U << (bit & 7))) == 0) return false;
        }
        return true;
    }
    uint64_t memory_bytes() const { return bits_.size(); }
    uint64_t blocks() const { return blocks_; }
    unsigned hashes() const { return k_; }
    double theoretical_fpr(uint64_t /*distinct*/) const {
        // Occupancy-conditioned estimate: average (fraction of set bits)^k
        // across the actual blocks. It incorporates block-to-block load
        // variation, unlike the ordinary global Bloom approximation.
        long double total = 0.0L;
        for (uint64_t b=0; b<blocks_; ++b) {
            const uint8_t *base = bits_.data() + static_cast<size_t>(b * (BLOCK_BITS/8));
            unsigned set_bits = 0;
            for (size_t j=0; j<BLOCK_BITS/8; ++j)
                set_bits += static_cast<unsigned>(__builtin_popcount(static_cast<unsigned>(base[j])));
            long double fraction = static_cast<long double>(set_bits) / BLOCK_BITS;
            total += std::pow(fraction, static_cast<int>(k_));
        }
        return static_cast<double>(total / blocks_);
    }
private:
    uint64_t seed_, blocks_=0;
    unsigned k_=0;
    std::vector<uint8_t> bits_;
};

class PackedFingerprints {
public:
    void assign(const std::vector<uint16_t> &values, unsigned bits) {
        bits_ = bits;
        count_ = values.size();
        const uint64_t total = static_cast<uint64_t>(count_) * bits_;
        bytes_.assign(static_cast<size_t>((total + 7) / 8), 0);
        uint64_t accumulator = 0;
        unsigned held = 0;
        size_t out = 0;
        const uint16_t mask = static_cast<uint16_t>((1U << bits_) - 1U);
        for (uint16_t v : values) {
            accumulator |= (static_cast<uint64_t>(v & mask) << held);
            held += bits_;
            while (held >= 8) {
                bytes_[out++] = static_cast<uint8_t>(accumulator & 0xffU);
                accumulator >>= 8;
                held -= 8;
            }
        }
        if (held) bytes_[out] = static_cast<uint8_t>(accumulator & 0xffU);
    }
    uint16_t get(size_t index) const {
        uint64_t bit = static_cast<uint64_t>(index) * bits_;
        size_t byte = static_cast<size_t>(bit >> 3);
        unsigned shift = static_cast<unsigned>(bit & 7U);
        uint32_t word = bytes_[byte];
        if (byte+1 < bytes_.size()) word |= static_cast<uint32_t>(bytes_[byte+1]) << 8;
        if (byte+2 < bytes_.size()) word |= static_cast<uint32_t>(bytes_[byte+2]) << 16;
        return static_cast<uint16_t>((word >> shift) & ((1U << bits_) - 1U));
    }
    uint64_t bytes() const { return bytes_.size(); }
private:
    unsigned bits_=8;
    size_t count_=0;
    std::vector<uint8_t> bytes_;
};

class XorFilter {
public:
    bool build(const std::vector<uint64_t> &keys, unsigned fp_bits) {
        if (keys.empty()) return false;
        fp_bits_ = fp_bits; mask_ = static_cast<uint16_t>((1U << fp_bits_) - 1U);
        const size_t n = keys.size();
        const size_t block = static_cast<size_t>(std::ceil(1.23 * static_cast<double>(n) / 3.0)) + 1;
        array_len_ = 3 * block;
        std::vector<uint8_t> degree(array_len_);
        std::vector<uint64_t> xors(array_len_);
        std::vector<uint32_t> queue; queue.reserve(array_len_);
        std::vector<uint64_t> order_hash; order_hash.reserve(n);
        std::vector<uint8_t> order_side; order_side.reserve(n);
        std::vector<uint16_t> values(array_len_);
        for (uint64_t attempt=0; attempt<128; ++attempt) {
            seed_ = 0x9e3779b97f4a7c15ULL * (attempt+1) ^ 0x6a09e667f3bcc909ULL;
            std::fill(degree.begin(), degree.end(), 0);
            std::fill(xors.begin(), xors.end(), 0);
            queue.clear(); order_hash.clear(); order_side.clear();
            for (uint64_t key : keys) {
                uint64_t h = hash_key(key);
                size_t p[3]; positions(h, block, p);
                for (int j=0;j<3;++j) {
                    if (degree[p[j]] == 255) return false;
                    ++degree[p[j]]; xors[p[j]] ^= h;
                }
            }
            for (size_t i=0;i<array_len_;++i) if (degree[i] == 1) queue.push_back(static_cast<uint32_t>(i));
            size_t head=0;
            while (head < queue.size()) {
                size_t idx=queue[head++];
                if (degree[idx] != 1) continue;
                uint64_t h=xors[idx]; size_t p[3]; positions(h,block,p);
                uint8_t side=255;
                for (uint8_t j=0;j<3;++j) if (p[j]==idx) { side=j; break; }
                if (side==255) continue;
                order_hash.push_back(h); order_side.push_back(side);
                degree[idx]=0; xors[idx]=0;
                for (int j=0;j<3;++j) if (j!=side) {
                    size_t q=p[j];
                    if (degree[q]>0) --degree[q];
                    xors[q]^=h;
                    if (degree[q]==1) queue.push_back(static_cast<uint32_t>(q));
                }
            }
            if (order_hash.size()==n) break;
        }
        if (order_hash.size()!=n) return false;
        std::fill(values.begin(), values.end(), 0);
        for (size_t z=n; z-- > 0;) {
            uint64_t h=order_hash[z]; size_t p[3]; positions(h,block,p);
            uint16_t fp=fingerprint(h);
            for (int j=0;j<3;++j) if (j!=order_side[z]) fp ^= values[p[j]];
            values[p[order_side[z]]] = static_cast<uint16_t>(fp & mask_);
        }
        packed_.assign(values,fp_bits_);
        block_len_=block;
        return true;
    }
    bool contains(uint64_t key) const {
        uint64_t h=hash_key(key); size_t p[3]; positions(h,block_len_,p);
        uint16_t fp=fingerprint(h);
        return static_cast<uint16_t>(packed_.get(p[0]) ^ packed_.get(p[1]) ^ packed_.get(p[2])) == fp;
    }
    uint64_t memory_bytes() const { return packed_.bytes(); }
    uint64_t array_length() const { return array_len_; }
private:
    uint64_t hash_key(uint64_t k) const { return mix64(k ^ seed_); }
    uint16_t fingerprint(uint64_t h) const {
        // Derive fingerprint bits through a separate avalanche step rather
        // than reusing position-hash bits. This reduces avoidable correlation
        // between the three graph positions and the stored fingerprint.
        return static_cast<uint16_t>(mix64(h ^ 0xa0761d6478bd642fULL) & mask_);
    }
    static void positions(uint64_t h,size_t block,size_t p[3]) {
        p[0]=static_cast<size_t>(reduce64(h,block));
        p[1]=block+static_cast<size_t>(reduce64(rotl64(h,21),block));
        p[2]=2*block+static_cast<size_t>(reduce64(rotl64(h,42),block));
    }
    uint64_t seed_=0; size_t block_len_=0,array_len_=0; unsigned fp_bits_=8; uint16_t mask_=255;
    PackedFingerprints packed_;
};

class BinaryFuseFilter {
public:
    bool build(const std::vector<uint64_t> &keys, unsigned fp_bits) {
        if (keys.empty()) return false;
        fp_bits_=fp_bits; mask_=static_cast<uint16_t>((1U<<fp_bits_)-1U);
        const size_t n=keys.size();
        int exp=static_cast<int>(std::floor(std::log(static_cast<double>(std::max<size_t>(n,2))) / std::log(3.33) + 2.25));
        exp=std::max(2,std::min(exp,18));
        segment_len_=static_cast<size_t>(1ULL<<exp);
        double size_factor=std::max(1.125,0.875+0.25*std::log(1000000.0)/std::log(static_cast<double>(std::max<size_t>(n,2))));
        size_t capacity=static_cast<size_t>(std::ceil(static_cast<double>(n)*size_factor));
        size_t segments=(capacity+segment_len_-1)/segment_len_;
        segments=segments>2?segments-2:1;
        segment_count_=segments;
        segment_count_length_=segment_count_*segment_len_;
        array_len_=(segment_count_+2)*segment_len_;
        std::vector<uint8_t> degree(array_len_);
        std::vector<uint64_t> xors(array_len_);
        std::vector<uint32_t> queue; queue.reserve(array_len_);
        std::vector<uint64_t> order_hash; order_hash.reserve(n);
        std::vector<uint8_t> order_side; order_side.reserve(n);
        std::vector<uint16_t> values(array_len_);
        for (uint64_t attempt=0;attempt<128;++attempt) {
            seed_=0x243f6a8885a308d3ULL + attempt*0x9e3779b97f4a7c15ULL;
            std::fill(degree.begin(),degree.end(),0);
            std::fill(xors.begin(),xors.end(),0);
            queue.clear(); order_hash.clear(); order_side.clear();
            for (uint64_t key:keys) {
                uint64_t h=hash_key(key); size_t p[3]; positions(h,p);
                for (int j=0;j<3;++j) {
                    if (degree[p[j]]==255) return false;
                    ++degree[p[j]]; xors[p[j]]^=h;
                }
            }
            for(size_t i=0;i<array_len_;++i) if(degree[i]==1) queue.push_back(static_cast<uint32_t>(i));
            size_t head=0;
            while(head<queue.size()) {
                size_t idx=queue[head++];
                if(degree[idx]!=1) continue;
                uint64_t h=xors[idx]; size_t p[3]; positions(h,p);
                uint8_t side=255;
                for(uint8_t j=0;j<3;++j) if(p[j]==idx){side=j;break;}
                if(side==255) continue;
                order_hash.push_back(h); order_side.push_back(side);
                degree[idx]=0; xors[idx]=0;
                for(int j=0;j<3;++j) if(j!=side){
                    size_t q=p[j]; if(degree[q]>0)--degree[q]; xors[q]^=h;
                    if(degree[q]==1) queue.push_back(static_cast<uint32_t>(q));
                }
            }
            if(order_hash.size()==n) break;
        }
        if(order_hash.size()!=n) return false;
        std::fill(values.begin(),values.end(),0);
        for(size_t z=n;z-- >0;){
            uint64_t h=order_hash[z]; size_t p[3]; positions(h,p);
            uint16_t fp=fingerprint(h);
            for(int j=0;j<3;++j)if(j!=order_side[z])fp^=values[p[j]];
            values[p[order_side[z]]]=static_cast<uint16_t>(fp&mask_);
        }
        packed_.assign(values,fp_bits_);
        return true;
    }
    bool contains(uint64_t key) const {
        uint64_t h=hash_key(key); size_t p[3]; positions(h,p);
        uint16_t fp=fingerprint(h);
        return static_cast<uint16_t>(packed_.get(p[0])^packed_.get(p[1])^packed_.get(p[2]))==fp;
    }
    uint64_t memory_bytes() const{return packed_.bytes();}
    uint64_t array_length() const{return array_len_;}
    size_t segment_length() const{return segment_len_;}
    size_t segment_count() const{return segment_count_;}
private:
    uint64_t hash_key(uint64_t k)const{return mix64(k^seed_);}
    uint16_t fingerprint(uint64_t h) const {
        // Use an independent avalanche step so fingerprint bits are not
        // correlated with the high hash bits used for segment selection.
        return static_cast<uint16_t>(mix64(h ^ 0xd6e8feb86659fd93ULL) & mask_);
    }
    void positions(uint64_t h,size_t p[3])const{
        // Fuse-graph mapping: choose a start segment, then one position in
        // each of three consecutive segments. Two trailing segments provide
        // room for the last window.
        size_t segment=static_cast<size_t>(reduce64(h,segment_count_));
        uint64_t low=h&((1ULL<<54)-1);
        p[0]=segment*segment_len_+static_cast<size_t>(low&(segment_len_-1));
        p[1]=(segment+1)*segment_len_+static_cast<size_t>((low>>18)&(segment_len_-1));
        p[2]=(segment+2)*segment_len_+static_cast<size_t>((low>>36)&(segment_len_-1));
    }
    uint64_t seed_=0;size_t segment_len_=0,segment_count_=0,segment_count_length_=0,array_len_=0;
    unsigned fp_bits_=8;uint16_t mask_=255;PackedFingerprints packed_;
};

} // namespace amqextra
#endif
