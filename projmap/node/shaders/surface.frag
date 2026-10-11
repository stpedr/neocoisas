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

out vec4 frag;

void main() {
    vec2 px = vec2(gl_FragCoord.x, u_viewport.y - gl_FragCoord.y) * (u_out_size / u_viewport);
    vec3 p = u_hinv * vec3(px, 1.0);
    if (p.z <= 0.0) discard;
    vec2 uv = p.xy / p.z;
    if (any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)))) discard;

    vec2 tuv = uv * u_uvx.xy + u_uvx.zw;
    if (any(lessThan(tuv, vec2(0.0))) || any(greaterThan(tuv, vec2(1.0)))) discard;

    vec4 c = texture(u_tex, tuv);
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
