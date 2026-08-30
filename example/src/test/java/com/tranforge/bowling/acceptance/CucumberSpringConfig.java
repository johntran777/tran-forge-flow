package com.tranforge.bowling.acceptance;

import io.cucumber.spring.CucumberContextConfiguration;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * Binds Cucumber step definitions to a booted Spring context so acceptance steps can exercise the
 * REST edge on a random port. Pre-wired scaffolding — do not duplicate.
 */
@CucumberContextConfiguration
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
public class CucumberSpringConfig {
}
