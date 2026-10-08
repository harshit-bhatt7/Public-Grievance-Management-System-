import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { UserPlus } from "lucide-react";
import FormField from "../components/FormField.jsx";
import Alert from "../components/Alert.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { ApiError } from "../services/api.js";
import {
  validateConfirmPassword,
  validateEmail,
  validateName,
  validatePassword,
  validatePhone,
} from "../utils/validation.js";

const initialForm = { name: "", email: "", phone: "", password: "", confirmPassword: "" };

function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState(initialForm);
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function handleChange(event) {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  function validate() {
    const errors = {
      name: validateName(form.name),
      email: validateEmail(form.email),
      phone: validatePhone(form.phone),
      password: validatePassword(form.password),
      confirmPassword: validateConfirmPassword(form.password, form.confirmPassword),
    };
    setFieldErrors(errors);
    return Object.values(errors).every((error) => !error);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setFormError(null);
    setSuccessMessage(null);

    if (!validate()) return;

    setSubmitting(true);
    try {
      await register({
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || null,
        password: form.password,
      });
      setSuccessMessage("Account created. Redirecting to login...");
      setForm(initialForm);
      setTimeout(() => navigate("/login"), 1200);
    } catch (error) {
      if (error instanceof ApiError) {
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
          <UserPlus size={13} /> Citizen Registration
        </span>
        <h1>Create a Citizen Account</h1>
        <p className="auth-subtitle">Register to submit and track civic grievances in your area.</p>

        <Alert type="error">{formError}</Alert>
        <Alert type="success">{successMessage}</Alert>

        <form onSubmit={handleSubmit} noValidate>
          <FormField
            label="Name"
            name="name"
            value={form.name}
            onChange={handleChange}
            error={fieldErrors.name}
            autoComplete="name"
          />
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
            label="Phone (optional)"
            name="phone"
            type="tel"
            value={form.phone}
            onChange={handleChange}
            error={fieldErrors.phone}
            autoComplete="tel"
            placeholder="+919876543210"
          />
          <FormField
            label="Password"
            name="password"
            type="password"
            value={form.password}
            onChange={handleChange}
            error={fieldErrors.password}
            autoComplete="new-password"
          />
          <FormField
            label="Confirm Password"
            name="confirmPassword"
            type="password"
            value={form.confirmPassword}
            onChange={handleChange}
            error={fieldErrors.confirmPassword}
            autoComplete="new-password"
          />

          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? "Creating account..." : "Register"}
          </button>
        </form>

        <p className="auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </div>
    </div>
  );
}

export default RegisterPage;
