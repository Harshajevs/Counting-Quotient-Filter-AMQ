#ifndef BLOOM_FILTER_HPP
#define BLOOM_FILTER_HPP

#include <vector>
#include <string>
#include <functional>

class BloomFilter {
private:
    std::vector<bool> bits;
    size_t num_hashes;

    /* Two genuinely independent base hashes (different algorithms, not just
     * different seeds on the same recurrence -- the original version here
     * used two hash functions with the identical "hash*31 + c" recurrence
     * and only a different seed, which makes them highly correlated rather
     * than independent, and measurably inflates the real false-positive
     * rate above the textbook k-hash-function formula). */
    size_t base_hash1(const std::string& str) const {
        std::hash<std::string> h;
        return h(str);
    }

    // djb2
    size_t base_hash2(const std::string& str) const {
        size_t hash = 5381;
        for (unsigned char c : str) {
            hash = ((hash << 5) + hash) + c;
        }
        return hash;
    }

    /* Kirsch-Mitzenmacher double hashing: simulate k independent hash
     * functions from 2 genuinely independent ones via
     *   g_i(x) = h1(x) + i * h2(x)   (mod m),  i = 0..k-1
     * This is provably as good as k independent hashes in practice and
     * only needs two decent base hashes, which is why it's the standard
     * technique rather than hand-rolling k separate hash functions. */
    size_t nth_hash(size_t i, size_t h1, size_t h2) const {
        return (h1 + i * h2) % bits.size();
    }

public:
    BloomFilter(size_t size = 10000, size_t num_hash_functions = 4)
        : bits(size, false), num_hashes(num_hash_functions) {}

    void insert(const std::string& item) {
        size_t h1 = base_hash1(item);
        size_t h2 = base_hash2(item);
        for (size_t i = 0; i < num_hashes; i++) {
            bits[nth_hash(i, h1, h2)] = true;
        }
    }

    bool contains(const std::string& item) const {
        size_t h1 = base_hash1(item);
        size_t h2 = base_hash2(item);
        for (size_t i = 0; i < num_hashes; i++) {
            if (!bits[nth_hash(i, h1, h2)]) return false;
        }
        return true;
    }

    size_t size() const {
        return bits.size();
    }
};

#endif
