// Mapeamento exato por pixel: uv = H^-1 · (x, y, 1).
// Interpolar uv por vértice nos 2 triângulos do quad daria a "dobra" diagonal
// (interpolação afim); avaliar a homografia aqui é exato para qualquer quad
// convexo. Ver projmap/mapping/warp.py (render_surface_cpu é o espelho em CPU).
uniform mat3 u_hinv;        // pixel do projetor -> uv [0,1]^2
uniform vec2 u_out_size;    // espaço do projeto (ex.: 1920x1080)
uniform vec2 u_viewport;    // framebuffer real (janela de preview pode ser menor)
uniform sampler2D u_tex;
uniform vec4 u_uvx;         // tex = uv * u_uvx.xy + u_uvx.zw (cover/contain)
uniform float u_opacity;
uniform float u_feather;    // borda suave, em fração do uv
uniform int u_multiply;     // 1 = modo multiplicar
uniform vec4 u_adj_s;       // ajuste da superfície: brilho, contraste, saturação, gama
uniform float u_temp_s;     //   temperatura (-1 frio … +1 quente)
uniform vec4 u_adj_o;       // ajuste do projetor inteiro (mesma ordem)
uniform float u_temp_o;
uniform vec2 u_flip;        // (-1 = espelhado) em x e y: retroprojeção / projetor de teto
// Efeitos reativos ao áudio (espelho de projmap/mapping/fx.py; neutros = 1,0,1,0,(0,0),0,0).
uniform float u_fx_gain;
uniform float u_fx_hue;     // rad, em torno do eixo cinza
uniform float u_fx_zoom;    // >1 aproxima
uniform float u_fx_split;   // separação R/B em uv
uniform vec2 u_fx_shift;    // tremor em uv
uniform float u_fx_invert;
uniform float u_fx_flash;

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);

// Espelho exato de projmap/mapping/color.py::adjust (testado GPU vs. CPU).
vec3 adjust(vec3 c, vec4 adj, float temp) {
    c = (c - 0.5) * adj.y + 0.5;           // contraste
    c *= adj.x;                             // brilho (ganho)
    float l = dot(c, LUMA);
    c = vec3(l) + (c - vec3(l)) * adj.z;    // saturação
    c *= vec3(1.0 + 0.12 * temp, 1.0 + 0.02 * temp, 1.0 - 0.12 * temp);  // temperatura
    c = clamp(c, 0.0, 1.0);
    return pow(c, vec3(1.0 / adj.w));       // gama
}

vec3 hue_rotate(vec3 c, float a) {
    const vec3 K = vec3(0.57735026919);
    float co = cos(a);
    return c * co + cross(K, c) * sin(a) + K * dot(K, c) * (1.0 - co);
}

out vec4 frag;

void main() {
    vec2 px = vec2(gl_FragCoord.x, u_viewport.y - gl_FragCoord.y) * (u_out_size / u_viewport);
    // Com a saída espelhada, o pixel da tela corresponde ao pixel "lógico" do lado oposto.
    if (u_flip.x < 0.0) px.x = u_out_size.x - px.x;
    if (u_flip.y < 0.0) px.y = u_out_size.y - px.y;
    vec3 p = u_hinv * vec3(px, 1.0);
    if (p.z <= 0.0) discard;
    vec2 uv = p.xy / p.z;
    if (any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)))) discard;

    vec2 tuv = uv * u_uvx.xy + u_uvx.zw;
    if (any(lessThan(tuv, vec2(0.0))) || any(greaterThan(tuv, vec2(1.0)))) discard;

    vec2 suv = clamp((tuv - 0.5) / u_fx_zoom + 0.5 + u_fx_shift, 0.0, 1.0);
    vec4 c = texture(u_tex, suv);
    if (u_fx_split != 0.0) {
        c.r = texture(u_tex, clamp(suv + vec2(u_fx_split, 0.0), 0.0, 1.0)).r;
        c.b = texture(u_tex, clamp(suv - vec2(u_fx_split, 0.0), 0.0, 1.0)).b;
    }
    c.rgb *= u_fx_gain;
    if (u_fx_hue != 0.0) c.rgb = hue_rotate(c.rgb, u_fx_hue);
    c.rgb = clamp(c.rgb, 0.0, 1.0);
    c.rgb = c.rgb + (1.0 - 2.0 * c.rgb) * u_fx_invert;
    c.rgb = c.rgb + (1.0 - c.rgb) * u_fx_flash;
    c.rgb = adjust(adjust(c.rgb, u_adj_s, u_temp_s), u_adj_o, u_temp_o);
    float a = c.a * u_opacity;
    if (u_feather > 0.0) {
        float e = min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y));
        a *= smoothstep(0.0, u_feather, e);
    }
    if (u_multiply == 1) {
        frag = vec4(mix(vec3(1.0), c.rgb, a), 1.0);
    } else {
        frag = vec4(c.rgb * a, a);  // alfa pré-multiplicado
    }
}
