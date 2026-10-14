from manim import *
class CenaModelo(Scene):
    def construct(self):
        circ = Circle(radius=1.2, color=BLUE)
        sq = Square(side_length=1.6, color=ORANGE).shift(RIGHT * 2.2)
        self.play(Create(circ), FadeIn(sq))
        self.play(Rotate(sq, angle=PI / 3))
        self.wait(1)
