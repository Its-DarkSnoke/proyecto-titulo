(() => {
    const form = document.querySelector('form[action="/predecir"]');

    if (!form) return;

    const fields = Object.fromEntries(
        [...form.elements]
            .filter(element => element.name)
            .map(element => [element.name, element])
    );

    const touched = new Set();

    function rutValido(value) {
        if (!/^[1-9][0-9]{6,7}-[0-9K]$/.test(value)) {
            return false;
        }

        const [cuerpo, dv] = value.split("-");

        const total = [...cuerpo]
            .reverse()
            .reduce(
                (suma, numero, indice) =>
                    suma + Number(numero) * (2 + indice % 6),
                0
            );

        const resultado = 11 - total % 11;

        const esperado =
            resultado === 11
                ? "0"
                : resultado === 10
                    ? "K"
                    : String(resultado);

        return dv === esperado;
    }

    function mensajeError(name) {
        const value = fields[name].value.trim();

        if (name === "rut") {
            return rutValido(value.toUpperCase())
                ? ""
                : "RUT inválido. Usa el formato 12345678-5, sin puntos y con dígito verificador correcto.";
        }

        if (name === "nombre") {
            const nombre = value
                .normalize("NFC")
                .replace(/\s+/g, " ");

            const partes = nombre.split(/[ '\-’]/u);

            const valido =
                nombre.length >= 3 &&
                nombre.length <= 100 &&
                nombre.split(" ").length >= 2 &&
                partes.every(parte => /^\p{L}+$/u.test(parte));

            return valido
                ? ""
                : "Ingresa nombre y apellido. Solo letras, espacios, guiones o apóstrofes; máximo 100 caracteres.";
        }

        if (name === "edad") {
            const valido =
                /^[0-9]{1,3}$/.test(value) &&
                Number(value) <= 120;

            return valido
                ? ""
                : "Ingresa una edad entera entre 0 y 120 años.";
        }

        const numero = Number(value.replace(",", "."));

        const valido =
            /^[0-9]+(?:[.,][0-9]+)?$/.test(value) &&
            Number.isFinite(numero) &&
            numero > 0;

        return valido
            ? ""
            : "Ingresa un número mayor que cero. Puedes usar punto o coma decimal.";
    }

    function validar(name) {
        const field = fields[name];
        const error = mensajeError(name);

        document.getElementById(`error-${name}`).textContent = error;

        field.setAttribute(
            "aria-invalid",
            String(Boolean(error))
        );

        return !error;
    }

    Object.entries(fields).forEach(([name, field]) => {
        if (name === "rut") {
            field.maxLength = 10;
            field.placeholder = "Ej: 12345678-5";
        }

        if (name === "nombre") {
            field.maxLength = 100;
        }

        if (
            name === "edad" ||
            name.endsWith("_medio") ||
            name.endsWith("_media")
        ) {
            field.type = "text";
            field.inputMode =
                name === "edad" ? "numeric" : "decimal";
        }

        field.id = field.id || name;

        const label = field.parentElement.querySelector("label");

        if (label) {
            label.htmlFor = field.id;
        }

        let error = document.getElementById(`error-${name}`);

        if (!error) {
            error = document.createElement("p");
            error.id = `error-${name}`;
            error.className = "field-error";
            error.setAttribute("aria-live", "polite");

            field.insertAdjacentElement("afterend", error);
        }

        field.setAttribute("aria-describedby", error.id);

        field.addEventListener("blur", () => {
            if (name === "rut") {
                field.value = field.value.trim().toUpperCase();
            }

            if (name === "nombre") {
                field.value = field.value
                    .normalize("NFC")
                    .trim()
                    .replace(/\s+/g, " ");
            }

            touched.add(name);
            validar(name);
        });

        field.addEventListener("input", () => {
            if (touched.has(name)) {
                validar(name);
            }
        });
    });

    // Usar los mensajes personalizados cuando JavaScript esté disponible.
    form.noValidate = true;

    form.addEventListener("submit", event => {
        const invalidos = Object.keys(fields).filter(
            name => !validar(name)
        );

        Object.keys(fields).forEach(name => touched.add(name));

        if (invalidos.length > 0) {
            event.preventDefault();
            fields[invalidos[0]].focus();
        }
    });
})();