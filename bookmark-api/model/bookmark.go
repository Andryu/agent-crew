package model

import "time"

// Bookmark represents a URL bookmark with optional tags.
type Bookmark struct {
	ID        string    `json:"id"`
	URL       string    `json:"url"`
	Title     string    `json:"title"`
	Tags      []string  `json:"tags"`
	CreatedAt time.Time `json:"created_at"`
}
