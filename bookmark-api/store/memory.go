package store

import (
	"fmt"
	"sync"

	"bookmark-api/model"
)

// Store defines the interface for bookmark persistence.
type Store interface {
	Create(bookmark model.Bookmark) error
	List(tags []string) []model.Bookmark
	Delete(id string) error
}

// MemoryStore is a concurrency-safe in-memory implementation of Store.
type MemoryStore struct {
	mu        sync.RWMutex
	bookmarks map[string]model.Bookmark
}

// NewMemoryStore creates a new MemoryStore.
func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		bookmarks: make(map[string]model.Bookmark),
	}
}

// Create adds a bookmark to the store.
func (s *MemoryStore) Create(bookmark model.Bookmark) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.bookmarks[bookmark.ID] = bookmark
	return nil
}

// List returns bookmarks, optionally filtered by tags (AND condition).
func (s *MemoryStore) List(tags []string) []model.Bookmark {
	s.mu.RLock()
	defer s.mu.RUnlock()

	result := make([]model.Bookmark, 0)
	for _, b := range s.bookmarks {
		if matchesTags(b, tags) {
			result = append(result, b)
		}
	}
	return result
}

// Delete removes a bookmark by ID. Returns an error if not found.
func (s *MemoryStore) Delete(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.bookmarks[id]; !ok {
		return fmt.Errorf("bookmark not found")
	}
	delete(s.bookmarks, id)
	return nil
}

// matchesTags checks if a bookmark has all the specified tags.
func matchesTags(b model.Bookmark, tags []string) bool {
	if len(tags) == 0 {
		return true
	}
	tagSet := make(map[string]struct{}, len(b.Tags))
	for _, t := range b.Tags {
		tagSet[t] = struct{}{}
	}
	for _, t := range tags {
		if _, ok := tagSet[t]; !ok {
			return false
		}
	}
	return true
}
