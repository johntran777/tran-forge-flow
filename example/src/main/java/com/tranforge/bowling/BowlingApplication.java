package com.tranforge.bowling;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Spring bootstrap for the Tran Forge bowling kata. Excluded from PIT mutation targets — there is
 * nothing meaningful to mutate here. The domain core the pipeline builds must stay framework-free
 * (see the project article); this class and any controllers are the adapter edge.
 */
@SpringBootApplication
public class BowlingApplication {

    public static void main(String[] args) {
        SpringApplication.run(BowlingApplication.class, args);
    }
}
