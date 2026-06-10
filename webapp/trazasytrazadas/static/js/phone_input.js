/**
 * Formateo visual de campos de teléfono.
 *
 * Normaliza la entrada del usuario al formato con prefijo internacional y
 * grupos de dígitos legibles durante la edición.
 *
 * Autor: Marcos Zamorano Lasso
 * Versión: 1.0
 */
"use strict";

(function () {
  const DEFAULT_COUNTRY = "34";

  // Separa el prefijo del número en formato visual.
  function splitVisualPrefix(raw) {
    if (!raw.startsWith("(+")) {
      return null;
    }

    let index = 2;
    let country = "";

    while (index < raw.length && country.length < 2) {
      const char = raw[index];

      if (char < "0" || char > "9") {
        break;
      }

      country += char;
      index += 1;
    }

    if (raw[index] === ")") {
      index += 1;
    }

    return {
      country,
      digits: raw.slice(index).replace(/\D/g, ""),
      prefixOnly: true,
    };
  }

  // Normaliza el valor escrito en prefijo y dígitos.
  function splitPhoneValue(value) {
    const raw = String(value || "").trim();

    if (!raw) {
      return { country: DEFAULT_COUNTRY, digits: "", prefixOnly: false };
    }

    const visualParts = splitVisualPrefix(raw);
    if (visualParts) {
      return visualParts;
    }

    if (raw.startsWith("+")) {
      const allDigits = raw.slice(1).replace(/\D/g, "");

      if (allDigits.length <= 2) {
        return { country: allDigits, digits: "", prefixOnly: true };
      }

      const country = allDigits.slice(0, 2);
      return {
        country,
        digits: allDigits.slice(country.length),
        prefixOnly: false,
      };
    }

    return {
      country: DEFAULT_COUNTRY,
      digits: raw.replace(/\D/g, ""),
      prefixOnly: false,
    };
  }

  // Agrupa los dígitos del número para mejorar la lectura.
  function groupPhoneDigits(digits) {
    if (digits.length <= 3) {
      return digits;
    }

    const groups = [digits.slice(0, 3)];
    let remaining = digits.slice(3);

    while (remaining.length > 2) {
      groups.push(remaining.slice(0, 2));
      remaining = remaining.slice(2);
    }

    if (remaining) {
      groups.push(remaining);
    }

    return groups.join(" ");
  }

  // Construye el valor visible del teléfono formateado.
  function formatPhoneValue(value) {
    const parts = splitPhoneValue(value);

    if (!parts.digits) {
      if (!parts.prefixOnly) {
        return "";
      }

      if (!parts.country) {
        return "(+";
      }

      if (parts.country.length < 2) {
        return `(+${parts.country}`;
      }

      return `(+${parts.country}) `;
    }

    const country = parts.country || DEFAULT_COUNTRY;
    return `(+${country}) ${groupPhoneDigits(parts.digits)}`;
  }

  // Aplica el formato visual al campo de teléfono.
  function applyPhoneFormat(input) {
    const formatted = formatPhoneValue(input.value);
    input.value = formatted;

    if (document.activeElement === input) {
      input.setSelectionRange(formatted.length, formatted.length);
    }
  }

  // Asocia el formateo automático a un campo de teléfono.
  function bindPhoneInput(input) {
    input.setAttribute("inputmode", "tel");

    if (input.value) {
      applyPhoneFormat(input);
    }

    input.addEventListener("input", () => applyPhoneFormat(input));
    input.addEventListener("blur", () => applyPhoneFormat(input));
  }

  document.addEventListener("DOMContentLoaded", () => {
    document
      .querySelectorAll("input[data-phone-format]")
      .forEach(bindPhoneInput);
  });
}());
