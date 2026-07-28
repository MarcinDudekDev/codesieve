<?php
/**
 * Plugin Name: Log Normalizer
 * Description: WPCS-conformant fixture — scores badly under PSR, well under WordPress.
 *
 * Deliberately has NO declare(strict_types=1): that is not customary in
 * WordPress code, and WordPress mode must not penalise its absence.
 *
 * @package Log_Normalizer
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Normalises raw log lines into a display-ready shape.
 */
class Log_Normalizer {

	/**
	 * Maximum characters kept from a single log message.
	 */
	const MAX_MESSAGE_LENGTH = 200;

	/**
	 * Registers the WordPress hooks this class listens on.
	 */
	public function register_hooks(): void {
		add_action( 'admin_init', array( $this, 'prime_option_cache' ) );
		add_filter( 'log_normalizer_line', array( $this, 'normalize_line' ), 10, 1 );
	}

	/**
	 * Reads the stored severity threshold once so later calls are cheap.
	 */
	public function prime_option_cache(): string {
		$stored_threshold = get_option( 'log_normalizer_threshold', 'warning' );

		return sanitize_text_field( $stored_threshold );
	}

	/**
	 * Trims and escapes a single raw log line for display.
	 */
	public function normalize_line( string $raw_line ): string {
		$collapsed_line = trim( preg_replace( '/\s+/', ' ', $raw_line ) );
		if ( '' === $collapsed_line ) {
			return '';
		}

		$truncated_line = substr( $collapsed_line, 0, self::MAX_MESSAGE_LENGTH );

		return esc_html( $truncated_line );
	}

	/**
	 * Decides whether a severity label clears the configured threshold.
	 */
	public function should_display_severity( string $severity_label, string $threshold_label ): bool {
		$ranked_severities = array( 'debug', 'info', 'warning', 'error' );
		$severity_rank     = array_search( $severity_label, $ranked_severities, true );
		$threshold_rank    = array_search( $threshold_label, $ranked_severities, true );

		if ( false === $severity_rank || false === $threshold_rank ) {
			return false;
		}

		return $severity_rank >= $threshold_rank;
	}
}
