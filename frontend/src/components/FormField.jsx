function FormField({ label, name, type = "text", value, onChange, error, autoComplete, placeholder }) {
  return (
    <div className="form-field">
      <label htmlFor={name}>{label}</label>
      <input
        id={name}
        name={name}
        type={type}
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
        placeholder={placeholder}
        className={error ? "input-error" : ""}
      />
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}

export default FormField;
