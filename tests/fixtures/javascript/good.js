/**
 * Well-structured JavaScript file for CodeSieve testing.
 * Should score high across all applicable sieves.
 */

const MAX_RETRIES = 3;
const DEFAULT_TIMEOUT = 5000;

/**
 * Format a user's full name.
 */
function formatFullName(firstName, lastName) {
    if (!firstName || !lastName) {
        return '';
    }
    return `${firstName} ${lastName}`;
}

/**
 * Calculate the average of an array of numbers.
 */
function calculateAverage(numbers) {
    if (numbers.length === 0) {
        return 0;
    }
    const sum = numbers.reduce((acc, val) => acc + val, 0);
    return sum / numbers.length;
}

/**
 * Simple user class with clean naming.
 */
class UserProfile {
    /** Initialise with name and email. */
    constructor(name, email) {
        this.name = name;
        this.email = email;
    }

    /** Return the display name or a fallback. */
    getDisplayName() {
        return this.name || 'Anonymous';
    }

    /** Check that name and email are present. */
    isValid() {
        return this.name && this.email;
    }

    /** Factory helper to create a UserProfile instance. */
    static create(name, email) {
        return new UserProfile(name, email);
    }
}

/**
 * Fetch data with proper error handling.
 */
async function fetchUserData(userId) {
    try {
        const response = await fetch(`/api/users/${userId}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Failed to fetch user:', error.message);
        throw error;
    }
}

/**
 * Parse configuration from an object.
 */
function parseConfig(rawConfig) {
    const timeout = rawConfig.timeout || DEFAULT_TIMEOUT;
    const retries = rawConfig.retries || MAX_RETRIES;

    return {
        timeout,
        retries,
        debug: rawConfig.debug || false,
    };
}

/**
 * Filter and transform items.
 */
function processItems(items) {
    return items
        .filter((item) => item.active)
        .map((item) => ({
            id: item.id,
            label: item.name.toUpperCase(),
        }));
}

module.exports = { UserProfile, formatFullName, calculateAverage, fetchUserData, parseConfig, processItems };
