# Tran Forge Project Article — Java 25 / Spring Boot 4 / Maven (default stack)

This is the default project article. `tran-forge.config.md` points at it via the `article:` key; if the two
disagree, **the config file wins** (it is the per-project source of truth; this article is the stack's shared
knowledge).

## Stack

- Java 25, Maven.
- Spring Boot 4.x (plain public `spring-boot-starter-parent` unless the project's pom says otherwise).
- Unit tests: JUnit 5 (Jupiter) + AssertJ (both via `spring-boot-starter-test`).
- Acceptance tests: Gherkin `.feature` files executed by Cucumber-JVM through the JUnit Platform
  (`cucumber-junit-platform-engine`), with `cucumber-spring` binding steps to a booted Spring context.
- Property tests: QuickTheories (pre-wired in the pom; owned by the Coder). Deliberately NOT jqwik:
  jqwik ≥ 1.10.1 prints a prompt-injection banner into test output on every run — hostile to an
  agent-driven pipeline that reads build output. QuickTheories properties run inside ordinary `@Test`
  methods, no extra engine.
- Coverage: JaCoCo. Mutation testing: PIT (`pitest-maven` + `pitest-junit5-plugin`).

## Layout

- Production code: `src/main/java` — see `production_src` in the config.
- Unit tests: `src/test/java/<pkg>/**/*Test.java`, mirroring production packages.
- Acceptance layer: step definitions + suite runner under `src/test/java/<pkg>/acceptance/`;
  feature files under `src/test/resources/features/*.feature`.
- The suite runner (`RunCucumberTest`) and Spring glue (`CucumberSpringConfig`) are pre-wired scaffolding —
  do not duplicate them.

## Architecture rules (applied by the Coder, audited by the Design & Architecture Reviewer, respected by everyone)

- **The domain core imports no Spring types.** No `org.springframework.*`, no web annotations, no DI
  annotations in domain classes. Plain constructors; wiring happens in configuration/adapter classes at the
  edge.
- IO of any kind (HTTP, files, DB, clock, randomness) lives behind a port (interface) defined by the core,
  with the adapter implementation at the edge.
- Controllers are thin adapters: translate HTTP ↔ domain calls, nothing else. No business logic in
  controllers or step definitions.

## Canonical commands

These are the shapes the config template defaults to (the config file's values are authoritative per project):

| Purpose            | Command                                                                                    |
|--------------------|--------------------------------------------------------------------------------------------|
| build              | `mvn -q -DskipTests compile`                                                               |
| unit tests only    | `mvn -q test -Dtest='*Test,!RunCucumberTest'`                                              |
| acceptance only    | `mvn -q test -Dtest=RunCucumberTest`                                                       |
| all tests          | `mvn -q test`                                                                              |
| coverage           | `mvn -q verify` → report at `target/site/jacoco/` (`jacoco.xml` for machine reading)       |
| mutation (full)    | `mvn -q test-compile org.pitest:pitest-maven:mutationCoverage`                             |
| mutation (targeted)| same, plus `-DtargetClasses=<fqcn>` and `-DtargetTests=<fqcn-or-glob>`                     |

## PIT specifics

- Reports land at `target/pit-reports/` (XML + HTML; `timestampedReports=false` so the path is stable).
  Parse `mutations.xml` for survivor details (`status="SURVIVED"`).
- **The Cucumber suite is excluded from PIT** (`excludedTestClasses` covers the `acceptance` package). PIT's
  per-test coverage mapping does not work through the Cucumber engine — runs get slow and flaky. Killing
  mutants is the UNIT suite's job. This is also why unit tests must stay separate from acceptance tests.
  Consequence: **nothing automated ever grades the acceptance suite's teeth.** That is why the Mutator runs the
  manual *Gherkin sensitivity sweep* instead — break the rule a scenario states, run `acceptance_tests`, prove
  that scenario fails, revert. Do not "fix" this by pointing PIT at the Cucumber suite; the sweep is the
  supported substitute.
- The `@SpringBootApplication` bootstrap class is excluded from mutation targets — there is nothing meaningful
  to mutate in it.
- `failWhenNoMutations=false` is set so PIT runs green before any production code exists.
- Equivalent mutants exist (mutations that produce behaviorally identical code — e.g. `<` → `<=` on a bound
  that is provably never hit). Do not chase them forever: document each with a one-line justification instead.

## Mutation blind spots — tests PIT cannot stand in for

PIT mutates the JVM **bytecode of production classes** — the service/domain layer. Some behavior never becomes
a mutable instruction, so a 100% mutation score on the surrounding class proves nothing about it. These need a
**mandatory dedicated test regardless of the mutation score**; the Coder owns writing them, the Mutator flags
their absence as a finding for the lead.

- **Repository `@Query` / JPQL / derived-finder methods.** The query lives in an annotation string or a method
  name — not in mutable bytecode. PIT cannot mutate it, so a wrong `WHERE`, a swapped join, or an off-by-one
  date bound never surfaces as a survived mutant. **A new or changed `@Query` (or derived query method) requires
  a DB-integration test that pins its behavior against real, seeded data** — DbUnit or `@DataJpaTest` with a
  known dataset, asserting the rows the query returns for representative inputs (including the boundary/empty
  cases). Testing the calling service with a mocked repository does NOT cover this — the mock cannot be wrong the
  way the query can.
- **REST endpoints.** Request mapping, status codes, (de)serialization, and validation wiring live in
  framework annotations and the container, not in mutable domain bytecode. **A new endpoint requires a
  controller test** (`@WebMvcTest`/MockMvc or the repo's established equivalent) covering the happy path and the
  error/status-code cases, **plus an acceptance scenario** exercising it end to end through the booted context.

## Discover existing test homes before writing tests (Scout)

The layout section above describes the *greenfield kata* shape. A real target repo already has its own test
homes and conventions, and they win. **Before creating any test file, scout the repo** for where sibling tests
of the same kind already live and how they are named — repository/DB tests, controller/web tests, and
acceptance tests each tend to have an established home and base-class/annotation pattern. Put new tests there
and follow that pattern; do not scatter a parallel structure alongside it. When no sibling of that kind exists,
fall back to the layout above and say so in the handoff.

## Test conventions

- One behavior concept per unit test; name states the rule (`spareAddsNextRollAsBonus`), not the mechanics.
- Prefer plain constructor-injected unit tests over `@SpringBootTest` — reserve the Spring context for the
  acceptance layer and true wiring tests. Fast unit tests keep PIT runs fast.
- Step definitions delegate immediately to domain objects or the REST edge; regex/Cucumber-expression capture
  for parameters; no logic and no assertions on internal state in steps — assert observable behavior.
- Run Maven with `-Duser.timezone=America/New_York` when a test involves time.
