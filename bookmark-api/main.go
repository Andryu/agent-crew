package main

import (
	"fmt"
	"log"
	"net/http"

	"bookmark-api/handler"
	"bookmark-api/store"
)

func main() {
	s := store.NewMemoryStore()
	h := handler.NewBookmarkHandler(s)

	mux := http.NewServeMux()
	mux.HandleFunc("POST /bookmarks", h.Create)
	mux.HandleFunc("GET /bookmarks", h.List)
	mux.HandleFunc("DELETE /bookmarks/{id}", h.Delete)

	addr := ":8080"
	fmt.Printf("bookmark-api listening on %s\n", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}
