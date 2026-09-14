from harness.java_adapter import JavaAdapter


def _adapter():
    return JavaAdapter(repo_path=None)


def test_is_compile_failure_detects_javac_banner():
    adapter = _adapter()
    assert adapter.is_compile_failure(RuntimeError("[ERROR] COMPILATION ERROR : \n...")) is True
    assert adapter.is_compile_failure(RuntimeError("connection timed out")) is False


def test_extract_test_ids_from_diff_finds_annotated_method():
    diff = """diff --git a/src/test/java/org/json/RecordTest.java b/src/test/java/org/json/RecordTest.java
index 1234567..89abcde 100644
--- a/src/test/java/org/json/RecordTest.java
+++ b/src/test/java/org/json/RecordTest.java
@@ -10,6 +10,12 @@ public class JSONObjectRecordTest {
     import org.json.junit.data.PersonRecord;

+    @Test
+    public void testRecordConversion() {
+        PersonRecord p = new PersonRecord("Ada", 30);
+        assertNotNull(p);
+    }
+
     @Test
     public void testExisting() {
         assertTrue(true);
"""
    adapter = _adapter()
    ids = adapter.extract_test_ids_from_diff(diff)
    assert ids == ["org.json.RecordTest::testRecordConversion"]


def test_extract_test_ids_from_diff_skips_intermediate_annotations():
    diff = """diff --git a/src/test/java/org/jsoup/HtmlTest.java b/src/test/java/org/jsoup/HtmlTest.java
--- a/src/test/java/org/jsoup/HtmlTest.java
+++ b/src/test/java/org/jsoup/HtmlTest.java
@@ -1,3 +1,7 @@
+    @Test
+    @DisplayName("checks the new insertNode overload")
+    public void testInsertNodeOverload() {
+    }
"""
    adapter = _adapter()
    ids = adapter.extract_test_ids_from_diff(diff)
    assert ids == ["org.jsoup.HtmlTest::testInsertNodeOverload"]


def test_extract_test_ids_from_diff_returns_empty_for_no_matches():
    adapter = _adapter()
    assert adapter.extract_test_ids_from_diff("diff --git a/README.md b/README.md\n+hello\n") == []
