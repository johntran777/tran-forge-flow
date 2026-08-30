package com.tranforge.bowling.acceptance;

import org.junit.platform.suite.api.ConfigurationParameter;
import org.junit.platform.suite.api.IncludeEngines;
import org.junit.platform.suite.api.SelectPackages;
import org.junit.platform.suite.api.Suite;

import static io.cucumber.junit.platform.engine.Constants.GLUE_PROPERTY_NAME;

/**
 * Pre-wired Cucumber suite runner. The Specifier drops .feature files into
 * src/test/resources/features/ and the Coder adds step definitions in this package — neither
 * should need to touch this class. failIfNoTests=false lets the suite pass vacuously on the
 * virgin kata (zero scenarios) so the preflight smoke is green.
 */
@Suite(failIfNoTests = false)
@IncludeEngines("cucumber")
@SelectPackages("features")
@ConfigurationParameter(key = GLUE_PROPERTY_NAME, value = "com.tranforge.bowling.acceptance")
public class RunCucumberTest {
}
