// Carrusel de adelanto al pasar el mouse: usado en las categorias del
// inicio, en las marcas de /marcas/, y en el menu de categorias del
// encabezado (presente en todas las paginas). Nunca dispara con click -- el
// click en la fila principal sigue yendo directo a la pagina completa, este
// efecto es solo un adelanto mientras el mouse esta encima.
//
// Se calcula el desplazamiento real en JS (getBoundingClientRect) en vez de
// aproximarlo en CSS puro, porque cada categoria/marca tiene una cantidad
// distinta de productos y un ancho de contenido distinto -- una animacion
// CSS con un porcentaje fijo se hubiera quedado corta o larga segun el caso.

type Opciones = {
  /**
   * El panel pasa a `position: fixed` con top/left calculados en JS al
   * activarse, en vez de depender de `position: absolute` respecto a su
   * contenedor. Hace falta en el menu del encabezado por dos motivos que no
   * existen en la seccion de categorias del inicio: 1) la barra tiene
   * `overflow-x: auto` para poder deslizarse en pantallas angostas, y eso
   * recorta verticalmente cualquier hijo `position:absolute` que se salga
   * de su caja -- confirmado, no es teorico, se probo sin este flag y el
   * panel quedaba invisible aunque el CSS `opacity` estuviera en 1. 2) cada
   * link del menu es angosto (~80-140px), asi que un panel mas ancho
   * alineado a la izquierda del ultimo item ("Marcas", "Tiroides") se
   * saldria del viewport por la derecha sin este calculo.
   */
  posicionFija?: boolean;
};

export function activarCarruselesPreview(selectorItem: string, opciones: Opciones = {}) {
  const items = document.querySelectorAll<HTMLElement>(selectorItem);
  const reducirMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  items.forEach((item) => {
    const contenedor = item.querySelector<HTMLElement>("[data-preview]");
    const track = item.querySelector<HTMLElement>("[data-preview-track]");
    if (!contenedor || !track) return;

    let activo = false;

    function posicionar() {
      if (!opciones.posicionFija || !contenedor) return;
      const triggerBox = item.getBoundingClientRect();
      // Ancho real del panel: hay que medirlo ya posicionado (aunque sea
      // invisible) porque su contenido define el ancho, no al reves.
      const anchoPanel = contenedor.offsetWidth;
      const margen = 12;
      let left = triggerBox.left;
      // Si alineado a la izquierda del link se saldria por la derecha de la
      // ventana, se ancla por la derecha del link en su lugar.
      if (left + anchoPanel > window.innerWidth - margen) {
        left = Math.max(margen, triggerBox.right - anchoPanel);
      }
      contenedor.style.position = "fixed";
      contenedor.style.top = `${triggerBox.bottom}px`;
      contenedor.style.left = `${left}px`;
      contenedor.style.right = "auto";
    }

    function deslizar() {
      if (!contenedor || !track) return;
      posicionar();
      // Se mide recien al activarse: si se midiera al cargar la pagina, un
      // reflow posterior (fuentes que terminan de cargar, etc.) dejaria el
      // calculo viejo. En touch (sin hover real) esto nunca se dispara.
      const distancia = track.scrollWidth - contenedor.clientWidth;
      if (distancia <= 0) return; // el contenido ya entra completo, nada que deslizar
      if (reducirMovimiento) {
        track.style.transform = `translateX(-${distancia}px)`;
        return;
      }
      // Velocidad pareja sin importar cuantos productos haya: mas
      // contenido, mas tiempo de recorrido, en vez de una duracion fija
      // que se sentiria apurada en las categorias con mas productos.
      const duracionMs = Math.min(2600, Math.max(700, distancia * 3.2));
      track.style.transitionDuration = `${duracionMs}ms`;
      track.style.transform = `translateX(-${distancia}px)`;
    }

    function resetear() {
      if (!track) return;
      track.style.transitionDuration = "220ms";
      track.style.transform = "translateX(0)";
    }

    item.addEventListener("mouseenter", () => {
      activo = true;
      deslizar();
    });
    item.addEventListener("mouseleave", () => {
      activo = false;
      resetear();
    });
    // Teclado: :focus-within ya muestra el panel (ver CSS); esto ademas
    // dispara el deslizamiento al tabular hasta un item del preview.
    item.addEventListener("focusin", () => {
      if (!activo) {
        activo = true;
        deslizar();
      }
    });
    item.addEventListener("focusout", (e) => {
      if (item.contains((e as FocusEvent).relatedTarget as Node | null)) return;
      activo = false;
      resetear();
    });
  });
}
