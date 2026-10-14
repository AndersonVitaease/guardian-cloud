from manim import *

class CenaDemoGuardian(Scene):
    def construct(self):
        t = Circle(radius=1.2, color=BLUE).shift(LEFT*2)
        g = Square(side_length=2, color=GREEN).shift(RIGHT*2)
        a = Arrow(LEFT*0.5, RIGHT*0.5, color=YELLOW)
        self.play(Create(t), FadeIn(g))
        self.play(Transform(g, a))
        self.play(Create(a))
        self.wait(1)
