<?php
declare(strict_types=1);

/**
 * A well-structured authentication module for testing CodeSieve.
 */

function validateEmail(string $email): bool
{
    if (strpos($email, '@') === false) {
        return false;
    }
    [$local, $domain] = explode('@', $email, 2);
    return strlen($local) > 0 && strpos($domain, '.') !== false;
}

function hashPassword(string $password, string $salt): string
{
    $combined = $salt . $password;
    return hash('sha256', $combined);
}

function createUser(string $username, string $email, string $password): array
{
    if (!validateEmail($email)) {
        throw new \InvalidArgumentException('Invalid email address');
    }

    $salt = 'random_salt_here';
    $passwordHash = hashPassword($password, $salt);

    return [
        'username' => $username,
        'email' => $email,
        'password_hash' => $passwordHash,
        'salt' => $salt,
        'active' => true,
    ];
}

class UserRepository
{
    private $database;

    public function __construct($database)
    {
        $this->database = $database;
    }

    public function findByEmail(string $email): ?array
    {
        return $this->database->query('users', ['email' => $email]);
    }

    public function save(array $user): bool
    {
        return $this->database->insert('users', $user);
    }

    public function delete(int $userId): bool
    {
        return $this->database->delete('users', $userId);
    }
}

function safeDivide(float $numerator, float $denominator): float
{
    try {
        if ($denominator == 0) {
            return 0.0;
        }
        $result = $numerator / $denominator;
    } catch (\DivisionByZeroError $e) {
        return 0.0;
    }
    return $result;
}

function parseConfig(string $filepath): array
{
    try {
        $content = file_get_contents($filepath);
        if ($content === false) {
            return ['error' => 'file not found'];
        }
        return json_decode($content, true) ?? [];
    } catch (\JsonException $e) {
        throw new \RuntimeException("Invalid config format: {$e->getMessage()}", 0, $e);
    }
}

function checkAge(int $age): string
{
    if ($age < 0) {
        return 'invalid';
    }
    if ($age < 18) {
        return 'minor';
    }
    return 'adult';
}
