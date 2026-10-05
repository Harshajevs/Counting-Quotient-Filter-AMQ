#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "gqf.h"
#include "gqf_int.h"

static int fail(const char *msg) {
    fprintf(stderr, "[test_cqf_counting] FAIL: %s\n", msg);
    return EXIT_FAILURE;
}

int main(void) {
    QF qf;
    if (!qf_malloc(&qf, 4096, 21, 0, QF_HASH_DEFAULT, 0))
        return fail("qf_malloc");

    const uint64_t a = 0x123456789abcdef0ULL;
    const uint64_t b = 0x0fedcba987654321ULL;

    for (int i = 0; i < 100; ++i) {
        if (qf_insert(&qf, a, 0, 1, QF_NO_LOCK) < 0)
            return fail("insert a");
    }
    for (int i = 0; i < 7; ++i) {
        if (qf_insert(&qf, b, 0, 1, QF_NO_LOCK) < 0)
            return fail("insert b");
    }

    if (qf_count_key_value(&qf, a, 0, 0) != 100)
        return fail("count(a) != 100");
    if (qf_count_key_value(&qf, b, 0, 0) != 7)
        return fail("count(b) != 7");

    for (int expected = 99; expected >= 0; --expected) {
        if (qf_remove(&qf, a, 0, 1, QF_NO_LOCK) < 0)
            return fail("remove a");
        if (qf_count_key_value(&qf, a, 0, 0) != (uint64_t)expected)
            return fail("a counter did not decrement exactly");
    }

    if (qf_count_key_value(&qf, a, 0, 0) != 0)
        return fail("a should be empty after decrements");

    if (qf_delete_key_value(&qf, b, 0, QF_NO_LOCK) < 0)
        return fail("delete b");
    if (qf_count_key_value(&qf, b, 0, 0) != 0)
        return fail("b should be absent after delete");

    qf_free(&qf);
    puts("[test_cqf_counting] PASS");
    return EXIT_SUCCESS;
}
