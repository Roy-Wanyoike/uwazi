export default function NotFound() {
  return (
    <div className="container empty" style={{ paddingTop: 80 }}>
      <h1 style={{ fontSize: 32, color: "var(--fg)" }}>404</h1>
      <p>Page not found.</p>
      <a href="/" className="btn btn-primary" style={{ marginTop: 16 }}>Go home →</a>
    </div>
  );
}
