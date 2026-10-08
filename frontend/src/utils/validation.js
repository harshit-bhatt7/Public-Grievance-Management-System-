const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_REGEX = /^\+?\d{7,15}$/;
const PASSWORD_MIN_LENGTH = 8;

export function validateName(name) {
  if (!name || name.trim().length < 2) {
    return "Name must be at least 2 characters long.";
  }
  return null;
}

export function validateEmail(email) {
  if (!email || !EMAIL_REGEX.test(email)) {
    return "Enter a valid email address.";
  }
  return null;
}

export function validatePhone(phone) {
  if (!phone) return null; // phone is optional
  if (!PHONE_REGEX.test(phone)) {
    return "Phone must be 7-15 digits, optionally starting with '+'.";
  }
  return null;
}

export function validatePassword(password) {
  if (!password || password.length < PASSWORD_MIN_LENGTH) {
    return `Password must be at least ${PASSWORD_MIN_LENGTH} characters long.`;
  }
  if (!/[A-Za-z]/.test(password)) {
    return "Password must contain at least one letter.";
  }
  if (!/\d/.test(password)) {
    return "Password must contain at least one digit.";
  }
  return null;
}

export function validateConfirmPassword(password, confirmPassword) {
  if (password !== confirmPassword) {
    return "Passwords do not match.";
  }
  return null;
}

// --- Grievance submission (Step 3) — mirrors backend rules in
// app/schemas/grievance.py and app/utils/file_storage.py ---

const TITLE_MIN_LENGTH = 5;
const TITLE_MAX_LENGTH = 200;
const DESCRIPTION_MIN_LENGTH = 20;
const DESCRIPTION_MAX_LENGTH = 5000;
const PINCODE_REGEX = /^[1-9][0-9]{5}$/;

export const ALLOWED_ATTACHMENT_EXTENSIONS = [".jpg", ".jpeg", ".png", ".pdf"];
export const ALLOWED_ATTACHMENT_MIME_TYPES = ["image/jpeg", "image/png", "application/pdf"];
export const MAX_ATTACHMENT_SIZE_MB = 10;

export function validateGrievanceTitle(title) {
  const trimmed = (title || "").trim();
  if (trimmed.length < TITLE_MIN_LENGTH) {
    return `Title must be at least ${TITLE_MIN_LENGTH} characters long.`;
  }
  if (trimmed.length > TITLE_MAX_LENGTH) {
    return `Title must be at most ${TITLE_MAX_LENGTH} characters long.`;
  }
  return null;
}

export function validateGrievanceDescription(description) {
  const trimmed = (description || "").trim();
  if (trimmed.length < DESCRIPTION_MIN_LENGTH) {
    return `Description must be at least ${DESCRIPTION_MIN_LENGTH} characters long.`;
  }
  if (trimmed.length > DESCRIPTION_MAX_LENGTH) {
    return `Description must be at most ${DESCRIPTION_MAX_LENGTH} characters long.`;
  }
  return null;
}

export function validateCategory(categoryId) {
  if (!categoryId) {
    return "Please select a category.";
  }
  return null;
}

export function validatePincode(pincode) {
  if (!pincode) return null; // optional
  if (!PINCODE_REGEX.test(pincode.trim())) {
    return "Enter a valid 6-digit PIN code.";
  }
  return null;
}

export function validateLatitude(latitude) {
  if (latitude === "" || latitude === null || latitude === undefined) return null;
  const value = Number(latitude);
  if (Number.isNaN(value) || value < -90 || value > 90) {
    return "Latitude must be between -90 and 90.";
  }
  return null;
}

export function validateLongitude(longitude) {
  if (longitude === "" || longitude === null || longitude === undefined) return null;
  const value = Number(longitude);
  if (Number.isNaN(value) || value < -180 || value > 180) {
    return "Longitude must be between -180 and 180.";
  }
  return null;
}

export function validateAttachmentFile(file) {
  if (!file) return null; // attachments are optional
  const extension = "." + file.name.split(".").pop().toLowerCase();
  if (!ALLOWED_ATTACHMENT_EXTENSIONS.includes(extension)) {
    return `Unsupported file type. Allowed: ${ALLOWED_ATTACHMENT_EXTENSIONS.join(", ")}.`;
  }
  if (!ALLOWED_ATTACHMENT_MIME_TYPES.includes(file.type)) {
    return "Unsupported file type. Only JPG, PNG, and PDF files are allowed.";
  }
  if (file.size > MAX_ATTACHMENT_SIZE_MB * 1024 * 1024) {
    return `File exceeds the ${MAX_ATTACHMENT_SIZE_MB} MB size limit.`;
  }
  return null;
}
