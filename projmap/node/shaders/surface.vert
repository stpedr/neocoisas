// Superfície: vértices chegam em pixels do projetor (origem no topo-esquerdo).
// Corpo em GLSL ES 3.00 / GLSL 3.30 comum; o #version é injetado pelo renderer
// (desktop: 330 core; Pi 5 / GLES: 300 es) — ver BLUEPRINT U1.
in vec2 in_pos;
uniform vec2 u_out_size;
uniform vec2 u_flip;  // (-1 = espelhado): retroprojeção (x) / projetor de teto (y)

void main() {
    vec2 ndc = vec2(in_pos.x / u_out_size.x * 2.0 - 1.0, 1.0 - in_pos.y / u_out_size.y * 2.0);
    gl_Position = vec4(ndc * u_flip, 0.0, 1.0);
}
