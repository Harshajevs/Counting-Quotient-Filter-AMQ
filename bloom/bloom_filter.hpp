#ifndef BLOOM_FILTER_HPP
#define BLOOM_FILTER_HPP

#include <vector>
#include <string>
#include <functional>

class BloomFilter {
private:
    std::vector<bool> bits;
    size_t num_hashes;
    
    // Hash functions
    size_t hash1(const std::string& str) const {
        std::hash<std::string> h;
        return h(str) % bits.size();
    }
    
    size_t hash2(const std::string& str) const {
        size_t hash = 5381;
        for (char c : str) {
            hash = ((hash << 5) + hash) + c;
        }
        return hash % bits.size();
    }
    
    size_t hash3(const std::string& str) const {
        size_t hash = 0;
        for (char c : str) {
            hash = hash * 31 + c;
        }
        return hash % bits.size();
    }
    
    size_t hash4(const std::string& str) const {
        size_t hash = 7;
        for (char c : str) {
            hash = hash * 31 + c;
        }
        return hash % bits.size();
    }
    
public:
    BloomFilter(size_t size = 10000, size_t num_hash_functions = 4)
        : bits(size, false), num_hashes(num_hash_functions) {}
    
    void insert(const std::string& item) {
        bits[hash1(item)] = true;
        bits[hash2(item)] = true;
        bits[hash3(item)] = true;
        bits[hash4(item)] = true;
    }
    
    bool contains(const std::string& item) const {
        return bits[hash1(item)] && 
               bits[hash2(item)] && 
               bits[hash3(item)] && 
               bits[hash4(item)];
    }
    
    size_t size() const {
        return bits.size();
    }
};

#endif
