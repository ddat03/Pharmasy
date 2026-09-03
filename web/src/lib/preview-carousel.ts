// Adelanto de productos al pasar el mouse: usado en las categorias del
// inicio, en las marcas de /marcas/, y en el menu de categorias del
// encabezado (presente en todas las paginas). Nunca dispara con click -- el
// click en la fila principal sigue yendo directo a la pagina completa, este
// efecto es solo un adelanto mientras el mouse esta encima.
//
// Dos modos de animacion, elegidos por contexto: en el home/marcas el panel
// es una fila horizontal angosta y el contenido se desliza en X (calculado
// en JS via getBoundingClientRect, porque cada categoria/marca tiene una
// cantidad distinta de productos y un porcentaje fijo en CSS se hubiera
// quedado corto o largo segun el caso). En el menu del encabezado el panel
// es una lista vertical -- a pedido del usuario, que la primera version
// (el mismo deslizamiento horizontal, en miniatura) no era lo que queria
// ahi -- y la animacion de entrada de cada fila la resuelve el CSS puro
// (@keyframes navcat-cae en Layout.astro, disparado por :hover), asi que
// este modulo solo necesita posicionar el panel, no animar nada.

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
  /**
   * Si el contenido del panel se desliza horizontalmente en JS
   * (`transform: translateX`). Por defecto true (home, marcas). En el menu
   * del encabezado es false: ahi el panel es una columna vertical y la
   * caida de cada fila es una animacion CSS pura disparada por :hover, sin
   * ningun transform que este modulo necesite calcular o aplicar.
   */
  desplazamientoHorizontal?: boolean;
};

export function activarCarruselesPreview(selectorItem: string, opciones: Opciones = {}) {
  const items = document.querySelectorAll<HTMLElement>(selectorItem);
  const reducirMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const conDesplazamiento = opciones.desplazamientoHorizontal ?? true;

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

    function activar() {
      if (!contenedor || !track) return;
      posicionar();
      if (!conDesplazamiento) return; // header: la caida de cada fila la anima el CSS solo
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
      if (!track || !conDesplazamiento) return;
      track.style.transitionDuration = "220ms";
      track.style.transform = "translateX(0)";
    }

    item.addEventListener("mouseenter", () => {
      activo = true;
      activar();
    });
    item.addEventListener("mouseleave", () => {
      activo = false;
      resetear();
    });
    // Teclado: :focus-within ya muestra el panel (ver CSS); esto ademas
    // dispara la animacion al tabular hasta un item del preview.
    item.addEventListener("focusin", () => {
      if (!activo) {
        activo = true;
        activar();
      }
    });
    item.addEventListener("focusout", (e) => {
      if (item.contains((e as FocusEvent).relatedTarget as Node | null)) return;
      activo = false;
      resetear();
    });
  });
}
