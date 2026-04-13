package store

import (
	"fmt"
	"sync"
	"testing"
	"time"

	"bookmark-api/model"
)

func newBookmark(id, url, title string, tags []string) model.Bookmark {
	return model.Bookmark{
		ID:        id,
		URL:       url,
		Title:     title,
		Tags:      tags,
		CreatedAt: time.Now().UTC(),
	}
}

func TestMemoryStore_Create(t *testing.T) {
	s := NewMemoryStore()
	b := newBookmark("1", "https://example.com", "Example", []string{"go"})

	if err := s.Create(b); err != nil {
		t.Fatalf("Create failed: %v", err)
	}

	result := s.List(nil)
	if len(result) != 1 {
		t.Fatalf("expected 1 bookmark, got %d", len(result))
	}
	if result[0].ID != "1" {
		t.Errorf("expected ID '1', got %q", result[0].ID)
	}
}

func TestMemoryStore_List_Empty(t *testing.T) {
	s := NewMemoryStore()
	result := s.List(nil)
	if result == nil {
		t.Fatal("expected non-nil empty slice, got nil")
	}
	if len(result) != 0 {
		t.Fatalf("expected 0 bookmarks, got %d", len(result))
	}
}

func TestMemoryStore_List_TagFilter(t *testing.T) {
	s := NewMemoryStore()
	s.Create(newBookmark("1", "https://a.com", "A", []string{"go", "tutorial"}))
	s.Create(newBookmark("2", "https://b.com", "B", []string{"go"}))
	s.Create(newBookmark("3", "https://c.com", "C", []string{"rust"}))

	tests := []struct {
		name     string
		tags     []string
		expected int
	}{
		{"no filter", nil, 3},
		{"single tag go", []string{"go"}, 2},
		{"single tag rust", []string{"rust"}, 1},
		{"AND filter go+tutorial", []string{"go", "tutorial"}, 1},
		{"no match", []string{"python"}, 0},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := s.List(tt.tags)
			if len(result) != tt.expected {
				t.Errorf("expected %d bookmarks, got %d", tt.expected, len(result))
			}
		})
	}
}

func TestMemoryStore_Delete(t *testing.T) {
	s := NewMemoryStore()
	s.Create(newBookmark("1", "https://a.com", "A", nil))

	tests := []struct {
		name    string
		id      string
		wantErr bool
	}{
		{"existing", "1", false},
		{"already deleted", "1", true},
		{"never existed", "999", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := s.Delete(tt.id)
			if (err != nil) != tt.wantErr {
				t.Errorf("Delete(%q) error = %v, wantErr %v", tt.id, err, tt.wantErr)
			}
		})
	}
}

func TestMemoryStore_ConcurrentAccess(t *testing.T) {
	s := NewMemoryStore()
	var wg sync.WaitGroup

	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			b := newBookmark(
				fmt.Sprintf("id-%d", i),
				"https://example.com",
				"Example",
				[]string{"go"},
			)
			s.Create(b)
			s.List(nil)
		}(i)
	}
	wg.Wait()

	result := s.List(nil)
	if len(result) != 100 {
		t.Errorf("expected 100 bookmarks, got %d", len(result))
	}
}
