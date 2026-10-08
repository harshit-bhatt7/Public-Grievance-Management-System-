import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import FormField from "../components/FormField.jsx";
import Alert from "../components/Alert.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { ApiError } from "../services/api.js";
import { validateEmail } from "../utils/validation.js";

const initialForm = { email: "", password: "" };

function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState(initialForm);
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function handleChange(event) {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  function validate() {
    const errors = {
      email: validateEmail(form.email),
      password: form.password ? null : "Password is required.",
    };
    setFieldErrors(errors);
    return Object.values(errors).every((error) => !error);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setFormError(null);

    if (!validate()) return;

    setSubmitting(true);
    try {
      await login({ email: form.email.trim(), password: form.password });
      navigate("/");
    } catch (error) {
      if (error instanceof ApiError) {
        // Backend already returns a generic "Invalid email or password."
        // message — never guess or add detail that could aid enumeration.
        setFormError(error.message);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <span className="badge neutral" style={{ marginBottom: "0.9rem" }}>
          <ShieldCheck size={13} /> Secure Citizen &amp; Officer Login
        </span>
        <h1>Log In</h1>
        <p className="auth-subtitle">Welcome back — track your grievances and civic activity.</p>

        <Alert type="error">{formError}</Alert>

        <form onSubmit={handleSubmit} noValidate>
          <FormField
            label="Email"
            name="email"
            type="email"
            value={form.email}
            onChange={handleChange}
            error={fieldErrors.email}
            autoComplete="email"
          />
          <FormField
            label="Password"
            name="password"
            type="password"
            value={form.password}
            onChange={handleChange}
            error={fieldErrors.password}
            autoComplete="current-password"
          />

          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? "Logging in..." : "Log In"}
          </button>
        </form>

        <p className="auth-switch">
          Don't have an account? <Link to="/register">Register</Link>
        </p>
      </div>
    </div>
  );
}

export default LoginPage;
