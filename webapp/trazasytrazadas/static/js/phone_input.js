"use strict";

(function () {
  const DEFAULT_COUNTRY = "34";

  function splitPhoneValue(value) {
    const raw = String(value || "").trim();

    if (!raw) {
      return { country: DEFAULT_COUNTRY, digits: "", prefixOnly: false };
    }

    const partialVisualMatch = raw.match(/^\(\+(\d{0,2})\)?\s*(.*)$/);
    if (partialVisualMatch) {
      return {
        country: partialVisualMatch[1],
        digits: partialVisualMatch[2].replace(/\D/g, ""),
        prefixOnly: true,
      };
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

  function applyPhoneFormat(input) {
    const formatted = formatPhoneValue(input.value);
    input.value = formatted;

    if (document.activeElement === input) {
      input.setSelectionRange(formatted.length, formatted.length);
    }
  }

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
