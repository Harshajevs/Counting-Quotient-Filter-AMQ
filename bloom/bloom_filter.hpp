#ifndef BLOOM_FILTER_HPP
#define BLOOM_FILTER_HPP

#include <cstddef>
#include <cstdint>
#include <vector>

/*
 * Compact Bloom filter for benchmark use.
 *
 * The benchmark paper configures Bloom filters by target FPR and uses the
 * optimal number of hash functions.  This implementation therefore:
 *   - accepts uint64_t keys directly (no timed std::string conversions),
 *   - stores bits in uint64_t words instead of std::vector<bool>, and
 *   - uses Kirsch-Mitzenmacher double hashing from two fast 64-bit mixers.
 *
 * The two base hashes are independent Mix64 evaluations with different
 * domain-separation constants.  h2 is forced odd so the probe sequence has
 * good coverage modulo arbitrary bit-array lengths.
 */
class BloomFilter {
private:
    std::vector<std::uint64_t> words_;
    std::size_t num_bits_;
    std::size_t num_hashes_;

    static inline std::uint64_t mix64(std::uint64_t x) {
        x += 0x9E3779B97F4A7C15ULL;
        x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
        x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
        return x ^ (x >> 31);
    }

    static inline std::uint64_t hash1(std::uint64_t key) {
        return mix64(key ^ 0xD6E8FEB86659FD93ULL);
    }

    static inline std::uint64_t hash2(std::uint64_t key) {
        return mix64(key ^ 0xA5A3564E27F8862DULL) | 1ULL;
    }

    inline std::size_t probe_index(std::uint64_t h1,
                                   std::uint64_t h2,
                                   std::size_t i) const {
        return static_cast<std::size_t>((h1 + static_cast<std::uint64_t>(i) * h2) % num_bits_);
    }

    inline void set_bit(std::size_t bit) {
        words_[bit >> 6] |= 1ULL << (bit & 63U);
    }

    inline bool get_bit(std::size_t bit) const {
        return (words_[bit >> 6] & (1ULL << (bit & 63U))) != 0;
    }

public:
    explicit BloomFilter(std::size_t size_bits = 10000,
                         std::size_t num_hash_functions = 4)
        : words_((size_bits + 63U) / 64U, 0ULL),
          num_bits_(size_bits),
          num_hashes_(num_hash_functions) {}

    void insert(std::uint64_t key) {
        const std::uint64_t h1 = hash1(key);
        const std::uint64_t h2 = hash2(key);
        for (std::size_t i = 0; i < num_hashes_; ++i) {
            set_bit(probe_index(h1, h2, i));
        }
    }

    bool contains(std::uint64_t key) const {
        const std::uint64_t h1 = hash1(key);
        const std::uint64_t h2 = hash2(key);
        for (std::size_t i = 0; i < num_hashes_; ++i) {
            if (!get_bit(probe_index(h1, h2, i))) return false;
        }
        return true;
    }

    std::size_t size() const { return num_bits_; }
    std::size_t num_hashes() const { return num_hashes_; }
    std::size_t size_in_bytes() const { return words_.size() * sizeof(std::uint64_t); }
};

#endif  // BLOOM_FILTER_HPP
