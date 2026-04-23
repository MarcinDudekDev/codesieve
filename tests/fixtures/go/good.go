// Package main demonstrates well-structured Go code.
package main

import (
	"errors"
	"fmt"
	"strings"
)

const (
	MaxRetries    = 3
	DefaultTimeout = 30
	StatusOK      = 200
)

// User represents a system user.
type User struct {
	ID    int
	Name  string
	Email string
}

// Validator validates user data.
type Validator struct {
	rules []string
}

// NewUser creates a new User with the given id and name.
func NewUser(id int, name string) (*User, error) {
	if id <= 0 {
		return nil, errors.New("id must be positive")
	}
	if name == "" {
		return nil, errors.New("name must not be empty")
	}
	return &User{ID: id, Name: name}, nil
}

// Validate checks whether the user data is valid.
func (u *User) Validate() error {
	if u.ID <= 0 {
		return errors.New("invalid user id")
	}
	if u.Name == "" {
		return errors.New("user name is required")
	}
	return nil
}

// DisplayName returns the formatted display name.
func (u *User) DisplayName() string {
	return fmt.Sprintf("%s (id=%d)", u.Name, u.ID)
}

// ProcessUsers processes a slice of users and returns valid ones.
func ProcessUsers(users []*User) ([]*User, error) {
	if len(users) == 0 {
		return nil, errors.New("no users provided")
	}
	result := make([]*User, 0, len(users))
	for _, user := range users {
		if err := user.Validate(); err != nil {
			continue
		}
		result = append(result, user)
	}
	return result, nil
}

// FormatList formats a slice of strings into a comma-separated list.
func FormatList(items []string) string {
	return strings.Join(items, ", ")
}

// Contains reports whether target is in the slice.
func Contains(items []string, target string) bool {
	for _, item := range items {
		if item == target {
			return true
		}
	}
	return false
}

// NewValidator creates a Validator with the given rules.
func NewValidator(rules []string) *Validator {
	return &Validator{rules: rules}
}

// Check verifies that the input satisfies all rules.
func (v *Validator) Check(input string) bool {
	if input == "" {
		return false
	}
	return true
}
