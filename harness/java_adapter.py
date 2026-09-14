"""T14: a third LanguageAdapter, in a compiled, build-tool-heavy ecosystem --
the real test of whether T2's four-method seam generalizes past interpreted
scripting languages, not just from one of those to another.

Deliberately narrower in scope for this first pass, the same way T13's
PythonAdapter was: only Maven, single-module repos have been live-verified.
Gradle detection and command construction are implemented (always via a
repo's own `./gradlew` wrapper, never a global Gradle install -- there
isn't one in this environment, and wrapper-equipped repos are the norm) but
unexercised against a live repo.

Both Maven's Surefire plugin and Gradle's built-in test task write JUnit XML
reports BY DEFAULT, with no extra reporter plugin needed -- a genuine
advantage over vitest/pytest, which both needed one injected (T2, T13).
"""

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from harness.language_adapter import Environment, LanguageAdapter

_JDKS_DIR = Path.home() / ".jdks"
_FALLBACK_MAVEN_HOME = Path.home() / ".local" / "apache-maven-3.9.9"
_REPORT_SEPARATOR = "\n<!--TSBENCH-REPORT-FILE-->\n"

# CI-only quality gates a real repo can bind straight into the build
# lifecycle (so a plain `mvn test` runs them whether asked to or not) --
# unrelated to whether the actual tests pass, but capable of failing the
# whole build anyway. jsoup's animal-sniffer Android-API check is what
# surfaced this; checkstyle/pmd/spotbugs/enforcer are the other common
# ones. Best-effort, not exhaustive -- a real repo can always invent a new
# one, the same open-ended caveat as any "install everything the target
# needs" step (T13's pytest-cov, TypeScriptAdapter's ERR_PNPM_IGNORED_BUILDS).
_MAVEN_SKIP_FLAGS = [
    "-Danimal.sniffer.skip=true",
    "-Dcheckstyle.skip=true",
    "-Dpmd.skip=true",
    "-Dspotbugs.skip=true",
    "-Denforcer.skip=true",
    "-Dlicense.skip=true",
    "-Dmaven.javadoc.skip=true",
]


class JavaAdapter(LanguageAdapter):
    def __init__(self, repo_path: Path, package_path: Path | None = None):
        self.repo_path = repo_path
        self.package_path = package_path or repo_path
        self._jdk_env_cache: dict[str, dict[str, str]] = {}

    def detect_environment(self, repo_path: Path) -> Environment:
        manager = self._detect_build_tool(self.repo_path)
        version = self._detect_jdk_version(self.repo_path, manager)
        compile_goal = "test-compile" if manager == "maven" else "testClasses"
        skip_flags = _MAVEN_SKIP_FLAGS if manager == "maven" else []
        # A multi-module Maven reactor (gson: gson/, test-jpms/, extras/, ...)
        # must still be invoked from the reactor root (a submodule's own pom
        # can't resolve sibling module coordinates on its own), but scoped to
        # just the one submodule + its dependencies via -pl/-am -- otherwise
        # every sibling module builds too, including ones (JPMS/GraalVM/
        # ProGuard integration tests, in gson's case) this benchmark has no
        # reason to build and that fail for reasons unrelated to the actual
        # library code being scored.
        module_flags = self._module_scope_flags(manager)
        return Environment(
            language_version=version,
            package_manager=manager,
            test_runner="surefire" if manager == "maven" else "gradle",
            install_cmd=self._build_invoke(manager) + [compile_goal] + module_flags + skip_flags,
            test_cmd_template=self._build_invoke(manager) + ["test"] + module_flags + skip_flags,
        )

    def install(self, sandbox, env: Environment) -> None:
        extra_env = self._build_jdk_env()
        result = sandbox.run(env.install_cmd, cwd=self.repo_path, timeout=900, extra_env=extra_env)
        if result.returncode != 0:
            # Maven's own [ERROR] diagnostics go to stdout, not stderr --
            # an install() error that only surfaced stderr was silently
            # empty for every real Maven failure, indistinguishable from
            # each other and useless for debugging.
            raise RuntimeError(f"install failed:\n{result.stdout[-3000:]}\n{result.stderr[-1000:]}")

    def run_tests(
        self, sandbox, env: Environment, test_ids: list[str] | None = None, timeout: int = 300
    ) -> str:
        # Clear stale reports first -- a crashed run must never leave a
        # previous run's XML lying around to be silently reparsed as current.
        self._clear_reports()

        extra_env = self._build_jdk_env()
        cmd = list(env.test_cmd_template)
        if env.package_manager == "maven":
            cmd += ["-B", "-fae"]  # batch mode; run every module even if one fails
        # Maven's -pl/-am scoping (see detect_environment) only resolves
        # correctly when invoked from the reactor root -- a submodule
        # directory doesn't know its siblings' coordinates on its own.
        cwd = self.repo_path if env.package_manager == "maven" else self.package_path
        result = sandbox.run(cmd, cwd=cwd, timeout=timeout, extra_env=extra_env)

        report_files = self._report_files()
        if not report_files:
            raise RuntimeError(
                f"no JUnit XML report produced (exit {result.returncode}).\nstderr:\n{result.stderr[-2000:]}"
            )
        return _REPORT_SEPARATOR.join(f.read_text(errors="replace") for f in report_files)

    def parse_results(self, raw_output: str, runner: str = "surefire") -> dict[str, bool]:
        out: dict[str, bool] = {}
        for chunk in raw_output.split(_REPORT_SEPARATOR):
            if not chunk.strip():
                continue
            root = ET.fromstring(chunk)
            for tc in root.iter("testcase"):
                classname = tc.get("classname")
                name = tc.get("name")
                if not classname or not name:
                    continue
                if tc.find("skipped") is not None:
                    continue  # neither pass nor fail -- didn't run, exclude
                failed = tc.find("failure") is not None or tc.find("error") is not None
                out[f"{classname}::{name}"] = not failed
        return out

    def is_compile_failure(self, error: Exception) -> bool:
        # install()'s own error message truncates to the last few thousand
        # characters of Maven's output (see install()) -- for a test file
        # with many repeated errors (the same missing symbol referenced on
        # a dozen lines), that tail can cut off the "COMPILATION ERROR"
        # banner itself while still containing these, which appear right
        # next to each individual [ERROR] line and survive truncation.
        text = str(error)
        return any(s in text for s in ("COMPILATION ERROR", "Compilation failure", "cannot find symbol"))

    def extract_test_ids_from_diff(self, diff_text: str) -> list[str]:
        """Pull `classname::methodName` targets straight out of a unified
        diff of test files, with no compiler or test runner involved --
        this only ever runs when the real ones can't even compile (T14's
        "compile failure as fails-at-base" finding). A JUnit test method is
        recognized by an added `@Test`/`@ParameterizedTest` annotation
        followed (skipping any other added annotation lines in between) by
        an added `void methodName(...)` line; the class name comes from the
        diff's own `+++ b/.../src/test/java/...Foo.java` file header.
        Best-effort: a wrong guess here just fails to be confirmed later by
        the real Surefire/JUnit XML output in green_run, never a false
        validation -- it can only under-count, not over-claim.
        """
        test_ids: list[str] = []
        current_class: str | None = None
        awaiting_method = False

        for line in diff_text.splitlines():
            file_header = re.match(r"^\+\+\+ b/(.+)$", line)
            if file_header:
                current_class = self._java_classname_from_path(file_header.group(1))
                awaiting_method = False
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue

            content = line[1:]
            if "@Test" in content or "@ParameterizedTest" in content:
                awaiting_method = True
                continue
            if awaiting_method:
                if content.strip().startswith("@"):
                    continue  # another annotation on its own line -- keep waiting
                m = re.search(r"\bvoid\s+(\w+)\s*\(", content)
                if m and current_class:
                    test_ids.append(f"{current_class}::{m.group(1)}")
                awaiting_method = False

        return test_ids

    def _java_classname_from_path(self, path: str) -> str | None:
        m = re.search(r"src/test/(?:java|kotlin|groovy)/(.+)\.java$", path)
        if not m:
            return None
        return m.group(1).replace("/", ".")

    # --- private helpers ---

    def _module_scope_flags(self, manager: str) -> list[str]:
        if manager != "maven" or self.package_path == self.repo_path:
            return []
        rel = self.package_path.relative_to(self.repo_path)
        return ["-pl", str(rel), "-am"]

    def _detect_build_tool(self, repo_path: Path) -> str:
        if (repo_path / "pom.xml").exists():
            return "maven"
        if (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
            return "gradle"
        raise ValueError(f"No pom.xml or build.gradle(.kts) found in {repo_path}")

    def _build_invoke(self, manager: str) -> list[str]:
        if manager == "maven":
            wrapper = self.repo_path / "mvnw"
            if wrapper.exists():
                wrapper.chmod(wrapper.stat().st_mode | 0o111)  # git archive can drop the exec bit
                return ["./mvnw"]
            return [str(_FALLBACK_MAVEN_HOME / "bin" / "mvn")]
        if manager == "gradle":
            wrapper = self.repo_path / "gradlew"
            if not wrapper.exists():
                raise RuntimeError(
                    f"{self.repo_path} has no ./gradlew wrapper and no global Gradle is installed "
                    "in this environment -- Gradle support only covers wrapper-equipped repos."
                )
            wrapper.chmod(wrapper.stat().st_mode | 0o111)
            return ["./gradlew"]
        raise ValueError(f"Unknown build tool: {manager}")

    def _clear_reports(self) -> None:
        for rel in ("target/surefire-reports", "build/test-results"):
            shutil.rmtree(self.package_path / rel, ignore_errors=True)

    def _report_files(self) -> list[Path]:
        files = list(self.package_path.glob("target/surefire-reports/TEST-*.xml"))
        files += list(self.package_path.glob("build/test-results/test/TEST-*.xml"))
        return files

    def _detect_jdk_version(self, repo_path: Path, manager: str, default: str = "17") -> str:
        java_version_file = repo_path / ".java-version"
        if java_version_file.exists():
            v = java_version_file.read_text().strip()
            if v:
                return self._normalize_version(v)

        # Only ever read the build file for the ACTUALLY detected tool.
        # A repo can carry a stale/secondary build.gradle alongside its real
        # pom.xml (JSON-java does) -- reading both regardless of which one
        # is actually in use meant a leftover Gradle file's own (unrelated,
        # and differently-formatted) version pin could silently override the
        # real one, or partially match "1.7" as JDK "1" (source/target style
        # <1.6> Maven config isn't even a property regex can find this way).
        candidates = ("pom.xml",) if manager == "maven" else ("build.gradle", "build.gradle.kts")
        for name in candidates:
            f = repo_path / name
            if not f.exists():
                continue
            text = f.read_text(errors="ignore")
            for pattern in (
                r"<maven\.compiler\.release>\s*(\d+)\s*</maven\.compiler\.release>",
                r"<maven\.compiler\.source>\s*([\d.]+)\s*</maven\.compiler\.source>",
                r"<java\.version>\s*([\d.]+)\s*</java\.version>",
                # The older maven-compiler-plugin <configuration> idiom
                # (bare <source>/<target>, not a <properties> entry) --
                # genuinely common, and what JSON-java's own pom.xml uses.
                r"<source>\s*([\d.]+)\s*</source>",
                r"<target>\s*([\d.]+)\s*</target>",
                r"sourceCompatibility\s*=\s*[\"']?([\d.]+)",
            ):
                m = re.search(pattern, text)
                if m:
                    return self._normalize_version(m.group(1))
        return default

    def _normalize_version(self, v: str) -> str:
        # Legacy Java versioning ("1.8") predates the modern major-version-only
        # scheme ("8", "11", "17") this method's caller reports. Purely
        # cosmetic now (see _build_jdk_env's docstring for why) but kept
        # accurate since it's still what ends up in the persisted schema.
        return v[2:] if v.startswith("1.") else v

    def _build_jdk_env(self) -> dict[str, str]:
        """The JDK actually used to RUN Maven/Gradle -- deliberately NOT the
        per-repo detected `language_version` (that field is metadata about
        the project's compile TARGET, kept for the schema/reporting).

        An earlier version of this method downloaded and used a JDK matching
        the detected version, mirroring TypeScriptAdapter's exact-node-pin
        approach. That was solving the wrong problem here: Java's compile
        TARGET (what bytecode a project wants to produce, e.g. "7") and the
        JDK needed to RUN the build tool (what actually executes javac/Maven
        plugins) are independent, and modern build tooling routinely needs a
        much newer one than the code it's building -- gson's own pom.xml
        requires `<jdkToolchain><version>[11,)</version>` while separately
        targeting `--release 7` bytecode, and Adoptium doesn't even serve
        JDK 6/7 (confirmed: 404) for projects pinned that old. The standard,
        correct fix (also how real CI systems build old Java code today):
        always build with ONE modern JDK and let Maven's own --release/
        source/target flags (already in the checked-out pom.xml, untouched
        by us) handle the actual bytecode compatibility.
        """
        if "build" not in self._jdk_env_cache:
            jdk_home = self._jdk_home("17")
            self._jdk_env_cache["build"] = {
                "JAVA_HOME": str(jdk_home),
                "PATH": f"{jdk_home / 'bin'}:{os.environ['PATH']}",
            }
        return self._jdk_env_cache["build"]

    def _jdk_home(self, version: str) -> Path:
        existing = list(_JDKS_DIR.glob(f"jdk-{version}*")) + list(_JDKS_DIR.glob(f"jdk{version}*"))
        if existing:
            return existing[0]

        _JDKS_DIR.mkdir(parents=True, exist_ok=True)
        archive = _JDKS_DIR / f"jdk{version}.tar.gz"
        url = (
            f"https://api.adoptium.net/v3/binary/latest/{version}/ga/linux/x64/"
            "jdk/hotspot/normal/eclipse?project=jdk"
        )
        result = subprocess.run(["curl", "-sL", url, "-o", str(archive)], capture_output=True)
        if result.returncode != 0 or archive.stat().st_size < 1_000_000:
            archive.unlink(missing_ok=True)  # never leave a failed download's debris behind
            raise RuntimeError(f"failed to download JDK {version} from Adoptium:\n{result.stderr}")
        subprocess.run(["tar", "xzf", str(archive), "-C", str(_JDKS_DIR)], check=True)
        archive.unlink()

        extracted = list(_JDKS_DIR.glob(f"jdk-{version}*")) + list(_JDKS_DIR.glob(f"jdk{version}*"))
        if not extracted:
            raise RuntimeError(f"JDK {version} archive extracted but no jdk-{version}* dir found")
        return extracted[0]
