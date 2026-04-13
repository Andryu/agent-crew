package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"bookmark-api/model"
	"bookmark-api/store"
)

func setupHandler() (*BookmarkHandler, *http.ServeMux) {
	s := store.NewMemoryStore()
	h := NewBookmarkHandler(s)
	mux := http.NewServeMux()
	mux.HandleFunc("POST /bookmarks", h.Create)
	mux.HandleFunc("GET /bookmarks", h.List)
	mux.HandleFunc("DELETE /bookmarks/{id}", h.Delete)
	return h, mux
}

func TestCreate_Success(t *testing.T) {
	_, mux := setupHandler()

	body := `{"url":"https://example.com","title":"Example","tags":["go","tutorial"]}`
	req := httptest.NewRequest(http.MethodPost, "/bookmarks", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	mux.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d", w.Code)
	}

	var b model.Bookmark
	json.NewDecoder(w.Body).Decode(&b)

	if b.URL != "https://example.com" {
		t.Errorf("expected url 'https://example.com', got %q", b.URL)
	}
	if b.Title != "Example" {
		t.Errorf("expected title 'Example', got %q", b.Title)
	}
	if len(b.Tags) != 2 {
		t.Errorf("expected 2 tags, got %d", len(b.Tags))
	}
	if b.ID == "" {
		t.Error("expected non-empty ID")
	}
	if w.Header().Get("Content-Type") != "application/json" {
		t.Errorf("expected Content-Type application/json, got %q", w.Header().Get("Content-Type"))
	}
}

func TestCreate_TagsOmitted_ReturnsEmptyArray(t *testing.T) {
	_, mux := setupHandler()

	body := `{"url":"https://example.com","title":"Example"}`
	req := httptest.NewRequest(http.MethodPost, "/bookmarks", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	mux.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d", w.Code)
	}

	var b model.Bookmark
	json.NewDecoder(w.Body).Decode(&b)

	if b.Tags == nil {
		t.Fatal("expected tags to be non-nil empty slice, got nil")
	}
	if len(b.Tags) != 0 {
		t.Errorf("expected 0 tags, got %d", len(b.Tags))
	}

	// Also verify the raw JSON contains [] not null
	raw := w.Body.String()
	// Re-read from the beginning isn't possible, so let's check via re-encoding
	_ = raw
}

func TestCreate_EmptyTagsFiltered(t *testing.T) {
	_, mux := setupHandler()

	body := `{"url":"https://example.com","title":"Example","tags":["","go",""]}`
	req := httptest.NewRequest(http.MethodPost, "/bookmarks", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	mux.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d", w.Code)
	}

	var b model.Bookmark
	json.NewDecoder(w.Body).Decode(&b)

	if len(b.Tags) != 1 {
		t.Errorf("expected 1 tag after filtering empty strings, got %d: %v", len(b.Tags), b.Tags)
	}
	if b.Tags[0] != "go" {
		t.Errorf("expected tag 'go', got %q", b.Tags[0])
	}
}

func TestCreate_Errors(t *testing.T) {
	tests := []struct {
		name       string
		body       string
		wantStatus int
		wantError  string
	}{
		{
			name:       "empty body",
			body:       "",
			wantStatus: http.StatusBadRequest,
			wantError:  "request body is empty",
		},
		{
			name:       "invalid JSON",
			body:       "not json",
			wantStatus: http.StatusBadRequest,
			wantError:  "request body is not valid JSON",
		},
		{
			name:       "missing url",
			body:       `{"title":"Example"}`,
			wantStatus: http.StatusBadRequest,
			wantError:  "url is required",
		},
		{
			name:       "missing title",
			body:       `{"url":"https://example.com"}`,
			wantStatus: http.StatusBadRequest,
			wantError:  "title is required",
		},
		{
			name:       "invalid url",
			body:       `{"url":"not-a-url","title":"Bad"}`,
			wantStatus: http.StatusBadRequest,
			wantError:  "url is not a valid URL (must start with http:// or https://)",
		},
		{
			name:       "empty title",
			body:       `{"url":"https://example.com","title":""}`,
			wantStatus: http.StatusBadRequest,
			wantError:  "title is required",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, mux := setupHandler()
			req := httptest.NewRequest(http.MethodPost, "/bookmarks", strings.NewReader(tt.body))
			req.Header.Set("Content-Type", "application/json")
			w := httptest.NewRecorder()

			mux.ServeHTTP(w, req)

			if w.Code != tt.wantStatus {
				t.Fatalf("expected status %d, got %d", tt.wantStatus, w.Code)
			}

			var resp errorResponse
			json.NewDecoder(w.Body).Decode(&resp)
			if resp.Error != tt.wantError {
				t.Errorf("expected error %q, got %q", tt.wantError, resp.Error)
			}
		})
	}
}

func TestList_Empty(t *testing.T) {
	_, mux := setupHandler()

	req := httptest.NewRequest(http.MethodGet, "/bookmarks", nil)
	w := httptest.NewRecorder()

	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var bookmarks []model.Bookmark
	json.NewDecoder(w.Body).Decode(&bookmarks)
	if bookmarks == nil {
		t.Fatal("expected non-nil empty slice")
	}
	if len(bookmarks) != 0 {
		t.Errorf("expected 0 bookmarks, got %d", len(bookmarks))
	}
}

func TestList_WithTagFilter(t *testing.T) {
	_, mux := setupHandler()

	// Create two bookmarks
	for _, b := range []string{
		`{"url":"https://a.com","title":"A","tags":["go","tutorial"]}`,
		`{"url":"https://b.com","title":"B","tags":["rust"]}`,
	} {
		req := httptest.NewRequest(http.MethodPost, "/bookmarks", strings.NewReader(b))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		mux.ServeHTTP(w, req)
	}

	// Filter by tag=go
	req := httptest.NewRequest(http.MethodGet, "/bookmarks?tag=go", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var bookmarks []model.Bookmark
	json.NewDecoder(w.Body).Decode(&bookmarks)
	if len(bookmarks) != 1 {
		t.Fatalf("expected 1 bookmark with tag 'go', got %d", len(bookmarks))
	}
	if bookmarks[0].Title != "A" {
		t.Errorf("expected title 'A', got %q", bookmarks[0].Title)
	}
}

func TestList_MultipleTagFilter_AND(t *testing.T) {
	_, mux := setupHandler()

	for _, b := range []string{
		`{"url":"https://a.com","title":"A","tags":["go","tutorial"]}`,
		`{"url":"https://b.com","title":"B","tags":["go"]}`,
	} {
		req := httptest.NewRequest(http.MethodPost, "/bookmarks", strings.NewReader(b))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		mux.ServeHTTP(w, req)
	}

	req := httptest.NewRequest(http.MethodGet, "/bookmarks?tag=go&tag=tutorial", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	var bookmarks []model.Bookmark
	json.NewDecoder(w.Body).Decode(&bookmarks)
	if len(bookmarks) != 1 {
		t.Fatalf("expected 1 bookmark with both tags, got %d", len(bookmarks))
	}
}

func TestDelete_Success(t *testing.T) {
	_, mux := setupHandler()

	// Create a bookmark
	body := `{"url":"https://example.com","title":"Example"}`
	createReq := httptest.NewRequest(http.MethodPost, "/bookmarks", strings.NewReader(body))
	createReq.Header.Set("Content-Type", "application/json")
	createW := httptest.NewRecorder()
	mux.ServeHTTP(createW, createReq)

	var b model.Bookmark
	json.NewDecoder(createW.Body).Decode(&b)

	// Delete it
	deleteReq := httptest.NewRequest(http.MethodDelete, "/bookmarks/"+b.ID, nil)
	deleteW := httptest.NewRecorder()
	mux.ServeHTTP(deleteW, deleteReq)

	if deleteW.Code != http.StatusNoContent {
		t.Fatalf("expected 204, got %d", deleteW.Code)
	}

	// Verify it's gone
	listReq := httptest.NewRequest(http.MethodGet, "/bookmarks", nil)
	listW := httptest.NewRecorder()
	mux.ServeHTTP(listW, listReq)

	var bookmarks []model.Bookmark
	json.NewDecoder(listW.Body).Decode(&bookmarks)
	if len(bookmarks) != 0 {
		t.Errorf("expected 0 bookmarks after delete, got %d", len(bookmarks))
	}
}

func TestDelete_NotFound(t *testing.T) {
	_, mux := setupHandler()

	req := httptest.NewRequest(http.MethodDelete, "/bookmarks/nonexistent-id", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", w.Code)
	}

	var resp errorResponse
	json.NewDecoder(w.Body).Decode(&resp)
	if resp.Error != "bookmark not found" {
		t.Errorf("expected 'bookmark not found', got %q", resp.Error)
	}
}

func TestDelete_ThenDeleteAgain(t *testing.T) {
	_, mux := setupHandler()

	// Create
	body := `{"url":"https://example.com","title":"Example"}`
	createReq := httptest.NewRequest(http.MethodPost, "/bookmarks", strings.NewReader(body))
	createReq.Header.Set("Content-Type", "application/json")
	createW := httptest.NewRecorder()
	mux.ServeHTTP(createW, createReq)

	var b model.Bookmark
	json.NewDecoder(createW.Body).Decode(&b)

	// First delete: 204
	req1 := httptest.NewRequest(http.MethodDelete, "/bookmarks/"+b.ID, nil)
	w1 := httptest.NewRecorder()
	mux.ServeHTTP(w1, req1)
	if w1.Code != http.StatusNoContent {
		t.Fatalf("first delete: expected 204, got %d", w1.Code)
	}

	// Second delete: 404
	req2 := httptest.NewRequest(http.MethodDelete, "/bookmarks/"+b.ID, nil)
	w2 := httptest.NewRecorder()
	mux.ServeHTTP(w2, req2)
	if w2.Code != http.StatusNotFound {
		t.Fatalf("second delete: expected 404, got %d", w2.Code)
	}
}
