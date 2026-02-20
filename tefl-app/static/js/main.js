// tefl app – main.js
// General UI utilities shared across all screens.

document.addEventListener("DOMContentLoaded", () => {
  // Highlight the active nav item based on current path
  // (The Jinja2 `active` variable already adds the class server-side,
  //  but this provides a client-side fallback.)
  const path = window.location.pathname;
  document.querySelectorAll(".bottom-nav__item").forEach((link) => {
    if (link.getAttribute("href") === path) {
      link.classList.add("bottom-nav__item--active");
    }
  });
});
