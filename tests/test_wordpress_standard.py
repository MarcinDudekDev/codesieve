"""Tests for --standard=wordpress (WPCS) vs the default PSR-1/PSR-12 grading."""

import os
from pathlib import Path

import pytest

from codesieve import standards
from codesieve.config import Config
from codesieve.engine import scan_file
from codesieve.langs import get_lang_pack
from codesieve.parser.treesitter import ParsedFile
from codesieve.sieves.naming import NamingSieve
from codesieve.sieves.type_hints import TypeHintsSieve

WP_FIXTURE = Path(__file__).parent / "wp_fixtures" / "class-log-normalizer.php"


def _write_php(tmp_path: Path, name: str, source: str) -> str:
    target = tmp_path / name
    target.write_text(source)
    return str(target)


def _names(source: str) -> list[str]:
    """Callable names as the vote sees them — from the parse tree, not the text."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".php", delete=False) as fh:
        fh.write(source)
    try:
        return ParsedFile(fh.name).callable_names()
    finally:
        os.unlink(fh.name)


def _corpus(entries: list[tuple[str, str]]) -> list[tuple[str, str, list[str]]]:
    """Build (path, source, names) triples for resolve_for_corpus."""
    return [(path, source, _names(source)) for path, source in entries]


# --- The two standards must be demonstrably different on the same file ---

def test_wp_fixture_scores_badly_under_psr():
    result = NamingSieve().analyze(ParsedFile(str(WP_FIXTURE), standard=standards.PSR))
    assert result.score <= 5.0, f"WPCS code should score poorly under PSR, got {result.score}"
    assert any("PSR-1" in f.message for f in result.findings)


def test_wp_fixture_scores_perfectly_under_wordpress():
    result = NamingSieve().analyze(ParsedFile(str(WP_FIXTURE), standard=standards.WORDPRESS))
    assert result.score == 10.0, f"WPCS code should be clean under WPCS, got {result.score}"
    assert result.findings == []


def test_wp_fixture_grade_improves_end_to_end():
    psr = scan_file(WP_FIXTURE, Config(standard=standards.PSR))
    wordpress = scan_file(WP_FIXTURE, Config(standard=standards.WORDPRESS))
    assert wordpress.aggregate_score > psr.aggregate_score
    assert wordpress.standard == standards.WORDPRESS
    assert psr.standard == standards.PSR


# --- Naming rules ---

@pytest.mark.parametrize("class_name", ["SQ_Probe", "Log_Normalizer", "Module_Base", "WP_Query"])
def test_wp_class_names_accepted(tmp_path, class_name):
    path = _write_php(tmp_path, f"{class_name}.php", f"<?php\nclass {class_name} {{}}\n")
    result = NamingSieve().analyze(ParsedFile(path, standard=standards.WORDPRESS))
    assert result.findings == []


@pytest.mark.parametrize("class_name", ["sq_probe", "logNormalizer", "Module_base"])
def test_wp_class_names_rejected(tmp_path, class_name):
    path = _write_php(tmp_path, f"{class_name}.php", f"<?php\nclass {class_name} {{}}\n")
    result = NamingSieve().analyze(ParsedFile(path, standard=standards.WORDPRESS))
    assert len(result.findings) == 1
    assert "WPCS" in result.findings[0].message


def test_wp_methods_must_be_snake_case(tmp_path):
    source = (
        "<?php\nclass Log_Normalizer {\n"
        "    public function normalize_line() { return 1; }\n"
        "    public function normalizeLine() { return 2; }\n"
        "}\n"
    )
    result = NamingSieve().analyze(ParsedFile(_write_php(tmp_path, "m.php", source), standard=standards.WORDPRESS))
    violations = [f for f in result.findings if "snake_case" in f.message]
    assert len(violations) == 1
    assert "normalizeLine" in violations[0].message


def test_wp_magic_methods_still_allowed(tmp_path):
    source = "<?php\nclass Log_Normalizer {\n    public function __construct() {}\n}\n"
    result = NamingSieve().analyze(ParsedFile(_write_php(tmp_path, "c.php", source), standard=standards.WORDPRESS))
    assert result.findings == []


# --- TypeHints: strict_types suppressed, coverage check intact ---

def test_wp_does_not_demand_strict_types(tmp_path):
    source = "<?php\nfunction render_notice( string $text ): string { return $text; }\n"
    path = _write_php(tmp_path, "t.php", source)
    psr = TypeHintsSieve().analyze(ParsedFile(path, standard=standards.PSR))
    wordpress = TypeHintsSieve().analyze(ParsedFile(path, standard=standards.WORDPRESS))
    assert any("strict_types" in f.message for f in psr.findings)
    assert not any("strict_types" in f.message for f in wordpress.findings)
    assert wordpress.score == 10.0


def test_wp_still_demands_param_and_return_types(tmp_path):
    source = "<?php\nfunction render_notice( $text ) { return $text; }\n"
    result = TypeHintsSieve().analyze(ParsedFile(_write_php(tmp_path, "u.php", source), standard=standards.WORDPRESS))
    assert result.score < 10.0
    assert any("missing type declaration" in f.message for f in result.findings)
    assert any("missing return type annotation" in f.message for f in result.findings)


# --- Auto-detection ---

def test_auto_detects_wordpress_from_source_markers():
    parsed = ParsedFile(str(WP_FIXTURE), standard=standards.AUTO)
    assert parsed.standard == standards.WORDPRESS


def test_auto_detects_wordpress_from_path(tmp_path):
    plugin_dir = tmp_path / "wp-content" / "plugins" / "demo"
    plugin_dir.mkdir(parents=True)
    path = _write_php(plugin_dir, "thing.php", "<?php\nclass Thing {}\n")
    assert ParsedFile(path, standard=standards.AUTO).standard == standards.WORDPRESS


def test_auto_falls_back_to_psr_for_plain_php(tmp_path):
    source = "<?php\nnamespace App;\nclass UserRepository { public function findById(int $id): int { return $id; } }\n"
    path = _write_php(tmp_path, "UserRepository.php", source)
    assert ParsedFile(path, standard=standards.AUTO).standard == standards.PSR


def test_auto_needs_more_than_one_weak_marker(tmp_path):
    """A lone get_option() call is not enough to declare a file WordPress."""
    path = _write_php(tmp_path, "Solo.php", "<?php\nfunction read() { return get_option('x'); }\n")
    assert ParsedFile(path, standard=standards.AUTO).standard == standards.PSR


def test_auto_rejects_wordpress_for_camelcase_methods(tmp_path):
    """A WP-shaped file whose methods are camelCase is a PSR-naming file."""
    source = (
        "<?php\n"
        "if ( ! defined( 'ABSPATH' ) ) { exit; }\n"
        "add_action( 'init', 'boot' );\n"
        "class Module_Base {\n"
        "    public function getInstance() { return 1; }\n"
        "    public function detectActive() { return 2; }\n"
        "    public function flushCache() { return 3; }\n"
        "}\n"
    )
    path = _write_php(tmp_path, "class-module-base.php", source)
    assert ParsedFile(path, standard=standards.AUTO).standard == standards.PSR


def test_naming_vote_ignores_ambiguous_and_magic_names():
    source = (
        "<?php\n"
        "class Thing {\n"
        "    public function __construct() {}\n"   # magic — excluded
        "    public function render() {}\n"        # no case signal — excluded
        "    public function get_Foo() {}\n"       # mixed — excluded
        "    public function normalize_line() {}\n"  # snake
        "    public function detectActive() {}\n"    # camel
        "}\n"
    )
    assert standards.count_naming_styles(_names(source)) == (1, 1)


def test_naming_vote_ties_go_to_wordpress():
    assert standards.follows_wpcs_naming(0, 0) is True
    assert standards.follows_wpcs_naming(3, 3) is True
    assert standards.follows_wpcs_naming(2, 3) is False


def test_corpus_vote_outweighs_a_single_snake_case_file():
    """The motivating case: one snake_case file inside a camelCase plugin."""
    sources = [
        ("wp-content/plugins/x/class-sq-probe.php",
         "<?php\nclass SQ_Probe {\n public function group_queries() {}\n public function validate_token() {}\n}\n"),
        ("wp-content/plugins/x/class-options.php",
         "<?php\nclass Options {\n public function updateValue() {}\n public function readValue() {}\n"
         " public function flushCache() {}\n public function primeCache() {}\n}\n"),
    ]
    corpus = _corpus(sources)
    assert standards.resolve_for_corpus(standards.AUTO, corpus) == standards.PSR
    # ...while that one file, judged alone, still reads as WPCS.
    assert standards.resolve(standards.AUTO, "php", *corpus[0]) == standards.WORDPRESS


def test_corpus_vote_keeps_wordpress_for_classic_wpcs_code():
    sources = [
        ("wp-content/plugins/x/class-log-normalizer.php",
         "<?php\nclass Log_Normalizer {\n public function normalize_line() {}\n public function prime_cache() {}\n}\n"),
        ("wp-content/plugins/x/class-admin-page.php",
         "<?php\nclass Admin_Page {\n public function render_page() {}\n public function register_hooks() {}\n}\n"),
    ]
    assert standards.resolve_for_corpus(standards.AUTO, _corpus(sources)) == standards.WORDPRESS


def test_corpus_vote_never_upgrades_non_wordpress_code():
    sources = [("src/UserRepository.php", "<?php\nclass UserRepository { public function find_by_id() {} }\n")]
    assert standards.resolve_for_corpus(standards.AUTO, _corpus(sources)) == standards.PSR


def test_explicit_standard_bypasses_the_corpus_vote():
    sources = [("src/x.php", "<?php\nclass X { public function doThing() {} }\n")]
    assert standards.resolve_for_corpus(standards.WORDPRESS, _corpus(sources)) == standards.WORDPRESS


def test_scan_directory_applies_one_standard_to_every_file(tmp_path):
    """Directory scans must not flip-flop between standards file by file."""
    plugin = tmp_path / "wp-content" / "plugins" / "demo"
    plugin.mkdir(parents=True)
    _write_php(plugin, "class-sq-probe.php",
               "<?php\nclass SQ_Probe {\n public function group_queries() {}\n}\n")
    _write_php(plugin, "class-options.php",
               "<?php\nclass Options {\n public function updateValue() {}\n"
               " public function readValue() {}\n public function flushCache() {}\n}\n")

    from codesieve.engine import scan
    report = scan(plugin, Config(standard=standards.AUTO))
    assert len(report.file_reports) == 2
    assert {fr.standard for fr in report.file_reports} == {standards.PSR}


# --- Regressions found in adversarial review (2026-07-28) ---

def test_vote_ignores_declarations_in_comments_and_strings(tmp_path):
    """A `function foo(` inside a comment or heredoc must not vote.

    Reading raw text let non-code steer the standard: a WP plugin embedding
    inline JS in a heredoc was graded PSR, and a comment could be padded to flip
    a camelCase file to WPCS.
    """
    source = (
        "<?php\n"
        "if ( ! defined( 'ABSPATH' ) ) { exit; }\n"
        "add_action( 'init', 'boot' );\n"
        "// function old_helper( function legacy_thing( function another_one(\n"
        "class Slider {\n"
        "    public function renderMarkup(): string {\n"
        "        return <<<HTML\n"
        "<script>function initSlider(){} function bindEvents(){} function tearDown(){}</script>\n"
        "HTML;\n"
        "    }\n"
        "    public function buildConfig(): array { return []; }\n"
        "}\n"
    )
    path = _write_php(tmp_path, "class-slider.php", source)
    parsed = ParsedFile(path, standard=standards.AUTO)
    # Only the two real methods are decisive, and both are camelCase.
    assert parsed.callable_names() == ["renderMarkup", "buildConfig"]
    assert standards.count_naming_styles(parsed.callable_names()) == (0, 2)
    assert parsed.standard == standards.PSR


def test_heredoc_javascript_does_not_misgrade_a_real_wpcs_plugin(tmp_path):
    """The legitimate-code half of the same bug: inline JS is routine in WP."""
    source = (
        "<?php\n"
        "/**\n * Plugin Name: Slider\n */\n"
        "add_action( 'init', 'boot' );\n"
        "class Slider_Widget {\n"
        "    public function render_widget(): string {\n"
        "        return <<<HTML\n"
        "<script>function initSlider(){} function bindEvents(){} function tearDown(){}</script>\n"
        "HTML;\n"
        "    }\n"
        "    public function register_hooks(): void {}\n"
        "}\n"
    )
    path = _write_php(tmp_path, "class-slider-widget.php", source)
    assert ParsedFile(path, standard=standards.AUTO).standard == standards.WORDPRESS


def test_vendored_code_does_not_outvote_the_codebase(tmp_path):
    """A Composer vendor/ tree must not decide the host plugin's standard."""
    plugin = tmp_path / "wp-content" / "plugins" / "demo"
    (plugin / "vendor" / "acme" / "lib").mkdir(parents=True)
    _write_php(plugin, "class-log-normalizer.php",
               "<?php\nclass Log_Normalizer {\n public function normalize_line() {}\n"
               " public function register_hooks() {}\n}\n")
    _write_php(plugin / "vendor" / "acme" / "lib", "Client.php",
               "<?php\nclass Client {\n" + "".join(
                   f" public function doThing{i}() {{}}\n" for i in range(10)) + "}\n")

    from codesieve.engine import scan
    report = scan(plugin, Config(standard=standards.AUTO))
    assert {fr.standard for fr in report.file_reports} == {standards.WORDPRESS}


def test_is_vendored_matches_only_whole_segments():
    assert standards.is_vendored("a/vendor/b/c.php")
    assert standards.is_vendored("node_modules/x.php")
    assert not standards.is_vendored("src/vendorish/c.php")
    assert not standards.is_vendored("src/my_vendor_helper.php")


def test_non_php_files_are_never_labelled_wordpress(tmp_path):
    """Standards describe PHP conventions; a Python sibling must not inherit one."""
    plugin = tmp_path / "wp-content" / "plugins" / "demo"
    plugin.mkdir(parents=True)
    _write_php(plugin, "class-thing.php",
               "<?php\nclass Thing {\n public function do_work() {}\n}\n")
    (plugin / "helper.py").write_text("def do_work() -> int:\n    return 1\n")

    from codesieve.engine import scan
    report = scan(plugin, Config(standard=standards.AUTO))
    by_lang = {fr.language: fr.standard for fr in report.file_reports}
    assert by_lang["php"] == standards.WORDPRESS
    assert by_lang["python"] == standards.PSR


def test_explicit_wordpress_does_not_label_non_php(tmp_path):
    path = str(tmp_path / "mod.py")
    Path(path).write_text("def run() -> int:\n    return 1\n")
    assert ParsedFile(path, standard=standards.WORDPRESS).standard == standards.PSR


def test_unknown_standard_in_yaml_warns_and_falls_back(tmp_path, capsys):
    config_file = tmp_path / ".codesieve.yml"
    config_file.write_text("standard: wpcs\n")
    config = Config.load(config_file)
    assert config.standard == standards.DEFAULT
    assert "unknown standard" in capsys.readouterr().err


def test_auto_is_a_noop_for_non_php(tmp_path):
    path = str(tmp_path / "mod.py")
    Path(path).write_text("def add_action(hook):\n    return hook\n")
    assert ParsedFile(path, standard=standards.AUTO).standard == standards.PSR


# --- Registry / config plumbing ---

def test_unknown_standard_falls_back_to_default_pack():
    assert get_lang_pack("php", "not-a-standard") is get_lang_pack("php")


def test_non_php_languages_ignore_the_standard():
    assert get_lang_pack("python", standards.WORDPRESS) is get_lang_pack("python")


def test_config_reads_standard_from_yaml(tmp_path):
    config_file = tmp_path / ".codesieve.yml"
    config_file.write_text("standard: wordpress\n")
    assert Config.load(config_file).standard == standards.WORDPRESS


def test_config_defaults_to_psr():
    assert Config().standard == standards.PSR
