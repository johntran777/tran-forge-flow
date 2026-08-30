package com.tranforge.bowling;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Proves the unit-test toolchain is green on the virgin kata so the Tran Forge preflight smoke
 * passes before any production code exists. Deliberately context-free (no Spring) so it stays fast.
 * The Coder may delete this once real tests exist.
 */
class SmokeTest {

    @Test
    void toolchainIsAlive() {
        assertThat(1 + 1).isEqualTo(2);
    }
}
