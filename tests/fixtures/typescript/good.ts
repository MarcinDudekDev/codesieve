/**
 * Well-structured TypeScript file for CodeSieve testing.
 * Should score high across all applicable sieves.
 */

interface UserData {
    id: number;
    name: string;
    email: string;
    active: boolean;
}

interface Config {
    timeout: number;
    retries: number;
    debug: boolean;
}

const MAX_RETRIES: number = 3;
const DEFAULT_TIMEOUT: number = 5000;

/** Format a user's full name from first and last components. */
function formatFullName(firstName: string, lastName: string): string {
    if (!firstName || !lastName) {
        return '';
    }
    return `${firstName} ${lastName}`;
}

/** Calculate the arithmetic mean of an array of numbers. */
function calculateAverage(numbers: number[]): number {
    if (numbers.length === 0) {
        return 0;
    }
    const sum = numbers.reduce((acc: number, val: number) => acc + val, 0);
    return sum / numbers.length;
}

class UserProfile {
    private name: string;
    private email: string;

    /** Initialise with name and email. */
    constructor(name: string, email: string) {
        this.name = name;
        this.email = email;
    }

    /** Return the display name or a fallback. */
    getDisplayName(): string {
        return this.name || 'Anonymous';
    }

    /** Check that name and email are both present. */
    isValid(): boolean {
        return Boolean(this.name && this.email);
    }

    /** Factory helper to create a UserProfile instance. */
    static create(name: string, email: string): UserProfile {
        return new UserProfile(name, email);
    }
}

/** Fetch user data from the API with error propagation. */
async function fetchUserData(userId: string): Promise<UserData> {
    try {
        const response = await fetch(`/api/users/${userId}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error: unknown) {
        if (error instanceof Error) {
            console.error('Failed to fetch user:', error.message);
        }
        throw error;
    }
}

/** Parse raw config values, applying defaults where missing. */
function parseConfig(rawConfig: Record<string, unknown>): Config {
    const timeout = (rawConfig.timeout as number) || DEFAULT_TIMEOUT;
    const retries = (rawConfig.retries as number) || MAX_RETRIES;

    return {
        timeout,
        retries,
        debug: Boolean(rawConfig.debug),
    };
}

/** Filter active items and return id/label pairs. */
function processItems(items: UserData[]): { id: number; label: string }[] {
    return items
        .filter((item: UserData) => item.active)
        .map((item: UserData) => ({
            id: item.id,
            label: item.name.toUpperCase(),
        }));
}

export { UserProfile, formatFullName, calculateAverage, fetchUserData, parseConfig, processItems };
