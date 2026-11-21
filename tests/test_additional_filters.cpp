#include "../filters/amq_extra.hpp"
#include <cstdint>
#include <iostream>
#include <random>
#include <vector>

int main() {
    std::vector<uint64_t> keys;
    keys.reserve(20000);
    for (uint64_t i = 1; i <= 20000; ++i)
        keys.push_back(i * 0x9e3779b97f4a7c15ULL);

    // Blocked Bloom: every inserted key must remain a positive.
    amqextra::BlockedBloomFilter blocked(keys.size(), 1.0 / 512.0);
    for (auto k : keys) blocked.insert(k);
    for (auto k : keys) {
        if (!blocked.contains(k)) {
            std::cerr << "Blocked Bloom false negative\n";
            return 1;
        }
    }

    // Counting Bloom: exercise counter overflow, duplicate deletion, and
    // preservation of all remaining keys while other keys are deleted.
    amqextra::CountingBloomFilter counting(keys.size(), 1.0 / 512.0);
    for (auto k : keys) counting.insert(k);
    const uint64_t hot = keys.front();
    for (int i = 0; i < 40; ++i) counting.insert(hot);
    for (auto k : keys) {
        if (!counting.contains(k)) {
            std::cerr << "Counting Bloom false negative before deletion\n";
            return 1;
        }
    }
    for (size_t i = 0; i < keys.size(); ++i) {
        if (!counting.erase(keys[i])) {
            std::cerr << "Counting Bloom failed to delete an inserted key\n";
            return 1;
        }
        if (i % 100 == 0) {
            // Sample keys that have not yet been deleted.
            for (size_t j = i + 1; j < std::min(keys.size(), i + 33); ++j) {
                if (!counting.contains(keys[j])) {
                    std::cerr << "Counting Bloom false negative after another key deletion\n";
                    return 1;
                }
            }
        }
    }
    for (int i = 0; i < 39; ++i) {
        if (!counting.erase(hot)) {
            std::cerr << "Counting Bloom failed to decrement a duplicate\n";
            return 1;
        }
    }
    if (!counting.contains(hot)) {
        std::cerr << "Counting Bloom removed hot key too early\n";
        return 1;
    }
    if (!counting.erase(hot)) {
        std::cerr << "Counting Bloom failed to remove final hot occurrence\n";
        return 1;
    }

    // Immutable filters are constructed from a distinct set and must never
    // return false negatives for the complete inserted key set.
    amqextra::XorFilter xor_filter;
    if (!xor_filter.build(keys, 9)) {
        std::cerr << "XOR construction failed\n";
        return 1;
    }
    for (auto k : keys) {
        if (!xor_filter.contains(k)) {
            std::cerr << "XOR false negative\n";
            return 1;
        }
    }

    amqextra::BinaryFuseFilter fuse;
    if (!fuse.build(keys, 9)) {
        std::cerr << "Binary Fuse construction failed\n";
        return 1;
    }
    for (auto k : keys) {
        if (!fuse.contains(k)) {
            std::cerr << "Binary Fuse false negative\n";
            return 1;
        }
    }

    // Deterministic negative sample: catches degenerate fingerprint or
    // position mappings without requiring a fragile exact FPR threshold.
    std::mt19937_64 rng(20261113);
    size_t xor_fp = 0, fuse_fp = 0, blocked_fp = 0;
    for (size_t i = 0; i < 20000; ++i) {
        uint64_t candidate = rng() | (1ULL << 63);
        if (xor_filter.contains(candidate)) ++xor_fp;
        if (fuse.contains(candidate)) ++fuse_fp;
        if (blocked.contains(candidate)) ++blocked_fp;
    }
    if (xor_fp > 300 || fuse_fp > 300 || blocked_fp > 500) {
        std::cerr << "Unexpectedly high false-positive sample: xor=" << xor_fp
                  << " fuse=" << fuse_fp << " blocked=" << blocked_fp << "\n";
        return 1;
    }

    std::cout << "All additional-filter unit tests passed.\n";
    std::cout << "Negative sample FPs: XOR=" << xor_fp
              << " BinaryFuse=" << fuse_fp << " BlockedBloom=" << blocked_fp << "\n";
    std::cout << "Blocked Bloom bytes=" << blocked.memory_bytes()
              << " Counting Bloom bytes~=" << counting.memory_bytes()
              << " XOR bytes=" << xor_filter.memory_bytes()
              << " Binary Fuse bytes=" << fuse.memory_bytes() << "\n";
    return 0;
}
