// toast.js - Sistema simple de notificaciones tipo toast

document.addEventListener("DOMContentLoaded", () => {
  const toastContainer = document.createElement("div");
  toastContainer.id = "toast-container";
  document.body.appendChild(toastContainer);

  window.mostrarToast = function(mensaje, tipo = "info", duracion = 3000) {
    const toast = document.createElement("div");
    toast.className = `toast ${tipo}`;
    toast.textContent = mensaje;

    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, duracion);
  };
});