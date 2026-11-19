import { useState } from "react";

function responseMessage(data, fallback) {
  return typeof data?.message === "string" ? data.message : fallback;
}

export default function UserManagementPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    phone: "",
  });
  const [role, setRole] = useState("member");
  const [permissions, setPermissions] = useState([]);
  const [status, setStatus] = useState("Active");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function searchUsers(event) {
    if (event) event.preventDefault();
    setMessage("");
    setError("");
    if (!query.trim()) {
      setError("กรุณากรอกคำค้น");
      setResults([]);
      return;
    }
    const response = await fetch(`/api/admin/users?q=${encodeURIComponent(query.trim())}`, {
      cache: "no-store",
      credentials: "same-origin",
    });
    const data = await response.json();
    if (!response.ok) {
      setError(responseMessage(data, "ไม่สามารถค้นหาบัญชีผู้ใช้ได้"));
      return;
    }
    setResults(data.results);
    setMessage(data.message || "");
  }

  async function selectAccount(username) {
    setError("");
    setMessage("");
    const response = await fetch(`/api/admin/users/${encodeURIComponent(username)}`, {
      cache: "no-store",
      credentials: "same-origin",
    });
    const data = await response.json();
    if (!response.ok) {
      setError(responseMessage(data, "ไม่สามารถเปิดข้อมูลบัญชีได้"));
      return;
    }
    const account = data.account;
    setSelected(account);
    setForm({
      first_name: account.first_name,
      last_name: account.last_name,
      email: account.email,
      phone: account.phone,
    });
    setRole(account.role || "member");
    setPermissions(account.permissions || []);
    setStatus(account.account_status);
  }

  async function updateAccount() {
    if (!selected) return;
    setError("");
    setMessage("");
    const response = await fetch(`/api/admin/users/${encodeURIComponent(selected.username)}`, {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const data = await response.json();
    if (!response.ok) {
      setError(responseMessage(data, "ไม่สามารถบันทึกข้อมูลบัญชีได้"));
      return;
    }
    setSelected(data.account);
    setMessage(data.message);
  }

  async function updateRole() {
    if (!selected) return;
    setError("");
    setMessage("");
    const response = await fetch(`/api/admin/users/${encodeURIComponent(selected.username)}/role`, {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, permissions }),
    });
    const data = await response.json();
    if (!response.ok) {
      setError(responseMessage(data, "ไม่สามารถบันทึก Role/Permission ได้"));
      return;
    }
    setSelected(data.account);
    setRole(data.account.role);
    setPermissions(data.account.permissions);
    setMessage(data.message);
  }

  async function updateStatus() {
    if (!selected) return;
    setError("");
    setMessage("");
    const response = await fetch(`/api/admin/users/${encodeURIComponent(selected.username)}/status`, {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    const data = await response.json();
    if (!response.ok) {
      setError(responseMessage(data, "ไม่สามารถบันทึกสถานะบัญชีได้"));
      return;
    }
    setSelected(data.account);
    setStatus(data.account.account_status);
    setMessage(data.message);
  }

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">ผู้ดูแลระบบ</p>
        <h1>จัดการสมาชิกและสิทธิ์ผู้ใช้</h1>
      </header>
      <form className="search-panel" onSubmit={searchUsers}>
        <label htmlFor="member-query">ชื่อ นามสกุล อีเมล หรือรหัสนักศึกษา</label>
        <input id="member-query" value={query} onChange={(event) => setQuery(event.target.value)} />
        <button type="submit">ค้นหา</button>
      </form>
      {error && <p className="feedback error-message" role="alert">{error}</p>}
      {message && <p className="feedback" role="status">{message}</p>}
      <section className="search-results">
        {results.map((account) => (
          <button
            type="button"
            key={account.username}
            className="search-result"
            onClick={() => selectAccount(account.username)}
          >
            {account.name} | {account.email} | {account.user_type} | {account.role} | {account.account_status}
          </button>
        ))}
      </section>
      {selected && (
        <section className="search-panel">
          <h2>{selected.name}</h2>
          <label>ชื่อ<input value={form.first_name} onChange={(event) => setForm({ ...form, first_name: event.target.value })} /></label>
          <label>นามสกุล<input value={form.last_name} onChange={(event) => setForm({ ...form, last_name: event.target.value })} /></label>
          <label>อีเมล<input value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
          <label>เบอร์โทรศัพท์<input value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} /></label>
          <button type="button" onClick={updateAccount}>บันทึกข้อมูลทั่วไป</button>
          <label>Role
            <select value={role} onChange={(event) => setRole(event.target.value)}>
              <option value="member">Member</option>
              <option value="librarian">Librarian</option>
              <option value="admin">Admin</option>
            </select>
          </label>
          <label>Permission
            <input value={permissions.join(",")} onChange={(event) => setPermissions(event.target.value.split(",").map((value) => value.trim()).filter(Boolean))} />
          </label>
          <button type="button" onClick={updateRole}>บันทึก Role/Permission</button>
          <label>สถานะบัญชี
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="Active">Active</option>
              <option value="Suspended">Suspended</option>
            </select>
          </label>
          <button type="button" onClick={updateStatus}>บันทึกสถานะ</button>
        </section>
      )}
    </main>
  );
}
