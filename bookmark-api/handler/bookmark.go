package handler

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"bookmark-api/model"
	"bookmark-api/store"

	"github.com/google/uuid"
)

// maxRequestBodyBytes is the maximum allowed request body size for Create (1MB).
const maxRequestBodyBytes = 1 << 20

// BookmarkHandler handles HTTP requests for bookmark operations.
type BookmarkHandler struct {
	store store.Store
}

// NewBookmarkHandler creates a new BookmarkHandler with the given store.
func NewBookmarkHandler(s store.Store) *BookmarkHandler {
	return &BookmarkHandler{store: s}
}

type errorResponse struct {
	Error string `json:"error"`
}

type createRequest struct {
	URL   string   `json:"url"`
	Title string   `json:"title"`
	Tags  []string `json:"tags"`
}

// Create handles POST /bookmarks.
func (h *BookmarkHandler) Create(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodyBytes)

	body, err := io.ReadAll(r.Body)
	if err != nil {
		var maxBytesErr *http.MaxBytesError
		if errors.As(err, &maxBytesErr) {
			writeError(w, http.StatusRequestEntityTooLarge, "request body too large (max 1MB)")
			return
		}
		writeError(w, http.StatusBadRequest, fmt.Errorf("failed to read request body: %w", err).Error())
		return
	}
	if len(body) == 0 {
		writeError(w, http.StatusBadRequest, "request body is empty")
		return
	}

	var req createRequest
	if err := json.Unmarshal(body, &req); err != nil {
		writeError(w, http.StatusBadRequest, "request body is not valid JSON")
		return
	}

	if req.URL == "" {
		writeError(w, http.StatusBadRequest, "url is required")
		return
	}
	if req.Title == "" {
		writeError(w, http.StatusBadRequest, "title is required")
		return
	}
	u, err := url.Parse(req.URL)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		writeError(w, http.StatusBadRequest, "url is not a valid URL (must start with http:// or https://)")
		return
	}

	// Filter out empty tags (edge case #9)
	tags := make([]string, 0)
	for _, t := range req.Tags {
		if t != "" {
			tags = append(tags, t)
		}
	}

	bookmark := model.Bookmark{
		ID:        uuid.New().String(),
		URL:       req.URL,
		Title:     req.Title,
		Tags:      tags,
		CreatedAt: time.Now().UTC(),
	}

	if err := h.store.Create(bookmark); err != nil {
		writeError(w, http.StatusInternalServerError, "failed to create bookmark")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(bookmark)
}

// List handles GET /bookmarks.
func (h *BookmarkHandler) List(w http.ResponseWriter, r *http.Request) {
	tags := r.URL.Query()["tag"]
	bookmarks := h.store.List(tags)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(bookmarks)
}

// Delete handles DELETE /bookmarks/{id}.
func (h *BookmarkHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")

	if err := h.store.Delete(id); err != nil {
		writeError(w, http.StatusNotFound, "bookmark not found")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func writeError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(errorResponse{Error: message})
}
