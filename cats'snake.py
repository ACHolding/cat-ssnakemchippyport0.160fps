import io
import random
import struct
import sys
import wave
from dataclasses import dataclass

import pygame

WIDTH = 600
HEIGHT = 400
FPS = 60
CELL = 20
GRID_W = WIDTH // CELL
GRID_H = HEIGHT // CELL

TITLE = "Cat's Snake py port 0.1"
SUBTITLE = "60 fps"

BLACK = (15, 15, 15)
WHITE = (240, 240, 240)
FAMICOM_BG = (30, 32, 48)
FAMICOM_PANEL = (58, 64, 92)
FAMICOM_RED = (200, 76, 12)
FAMICOM_GOLD = (236, 194, 80)
FAMICOM_GREEN = (88, 168, 104)
FAMICOM_LIGHT = (180, 220, 168)
FAMICOM_BLUE = (92, 148, 252)
FAMICOM_DARK = (20, 24, 36)
AUDIO_SAMPLE_RATE = 22050


@dataclass
class Food:
    x: int
    y: int


class ChiptuneAudio:
    def __init__(self):
        self.enabled = False
        self.sounds = {}

        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(
                    frequency=AUDIO_SAMPLE_RATE,
                    size=-16,
                    channels=1,
                    buffer=256,
                )
            self.sounds = self._build_sounds()
            self.enabled = True
        except pygame.error:
            self.sounds = {}

    def play(self, name):
        if not self.enabled:
            return

        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()

    def _build_sounds(self):
        return {
            "menu_move": self._make_sound(
                [
                    {"freq": 660, "duration": 0.04, "volume": 0.20, "duty": 0.125},
                    {"freq": 880, "duration": 0.03, "volume": 0.16, "duty": 0.25},
                ]
            ),
            "menu_select": self._make_sound(
                [
                    {"freq": 392, "duration": 0.05, "volume": 0.20, "duty": 0.25},
                    {"freq": 523, "duration": 0.05, "volume": 0.22, "duty": 0.125},
                    {"freq": 784, "duration": 0.08, "volume": 0.20, "duty": 0.25},
                ]
            ),
            "start": self._make_sound(
                [
                    {"freq": 262, "duration": 0.05, "volume": 0.18, "wave": "triangle"},
                    {"freq": 330, "duration": 0.05, "volume": 0.20, "wave": "triangle"},
                    {"freq": 392, "duration": 0.08, "volume": 0.24, "duty": 0.125},
                ]
            ),
            "eat": self._make_sound(
                [
                    {"freq": 988, "duration": 0.03, "volume": 0.18, "duty": 0.125},
                    {"freq": 1319, "duration": 0.05, "volume": 0.24, "duty": 0.25},
                ]
            ),
            "game_over": self._make_sound(
                [
                    {"freq": 392, "duration": 0.07, "volume": 0.22, "duty": 0.25, "slide": -40},
                    {"freq": 294, "duration": 0.09, "volume": 0.20, "duty": 0.25, "slide": -50},
                    {"freq": 196, "duration": 0.16, "volume": 0.24, "wave": "triangle", "slide": -35},
                    {"freq": 1, "duration": 0.05, "volume": 0.08, "wave": "noise"},
                ]
            ),
        }

    def _make_sound(self, sequence):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(AUDIO_SAMPLE_RATE)
            wav_file.writeframes(self._render_sequence(sequence))
        buffer.seek(0)
        return pygame.mixer.Sound(file=buffer)

    def _render_sequence(self, sequence):
        frames = bytearray()
        for step in sequence:
            frames.extend(self._render_step(step))
        return bytes(frames)

    def _render_step(self, step):
        freq = step.get("freq", 440)
        duration = step.get("duration", 0.05)
        volume = step.get("volume", 0.2)
        duty = step.get("duty", 0.125)
        wave_type = step.get("wave", "pulse")
        slide = step.get("slide", 0)

        sample_count = max(1, int(AUDIO_SAMPLE_RATE * duration))
        attack = max(1, int(sample_count * 0.08))
        release = max(1, int(sample_count * 0.20))
        frames = bytearray()

        for index in range(sample_count):
            t = index / AUDIO_SAMPLE_RATE
            progress = index / sample_count
            current_freq = max(1, freq + slide * progress)
            phase = (t * current_freq) % 1.0

            if wave_type == "triangle":
                sample = 1.0 - 4.0 * abs(phase - 0.5)
            elif wave_type == "noise":
                sample = random.uniform(-1.0, 1.0)
            else:
                sample = 1.0 if phase < duty else -1.0

            envelope = 1.0
            if index < attack:
                envelope = index / attack
            elif index >= sample_count - release:
                envelope = (sample_count - index - 1) / release

            amplitude = int(32767 * volume * sample * max(0.0, envelope))
            frames.extend(struct.pack("<h", amplitude))

        return frames


class SnakeGame:
    def __init__(self):
        pygame.mixer.pre_init(AUDIO_SAMPLE_RATE, size=-16, channels=1, buffer=256)
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()

        self.font_small = pygame.font.SysFont("couriernew", 16, bold=True)
        self.font_medium = pygame.font.SysFont("couriernew", 24, bold=True)
        self.font_large = pygame.font.SysFont("couriernew", 32, bold=True)
        self.font_title = pygame.font.SysFont("couriernew", 36, bold=True)

        self.menu_items = ["Play Game", "About", "Help", "Exit"]
        self.menu_index = 0
        self.state = "menu"
        self.audio = ChiptuneAudio()

        self.move_delay_frames = 7
        self.move_timer = 0

        self.reset_game()

    def reset_game(self):
        cx = GRID_W // 2
        cy = GRID_H // 2
        self.snake = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]
        self.direction = (1, 0)
        self.next_direction = (1, 0)
        self.score = 0
        self.game_over = False
        self.food = self.spawn_food()
        self.move_timer = 0

    def spawn_food(self):
        while True:
            x = random.randint(1, GRID_W - 2)
            y = random.randint(1, GRID_H - 2)
            if (x, y) not in self.snake:
                return Food(x, y)

    def run(self):
        while True:
            self.handle_events()
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit_game()

            if event.type == pygame.KEYDOWN:
                if self.state == "menu":
                    self.handle_menu_input(event)
                elif self.state == "playing":
                    self.handle_game_input(event)
                elif self.state in ("about", "help"):
                    if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                        self.state = "menu"
                        self.audio.play("menu_select")
                elif self.state == "game_over":
                    if event.key == pygame.K_RETURN:
                        self.reset_game()
                        self.state = "playing"
                        self.audio.play("start")
                    elif event.key == pygame.K_ESCAPE:
                        self.state = "menu"
                        self.audio.play("menu_select")

    def handle_menu_input(self, event):
        if event.key in (pygame.K_UP, pygame.K_w):
            self.menu_index = (self.menu_index - 1) % len(self.menu_items)
            self.audio.play("menu_move")
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.menu_index = (self.menu_index + 1) % len(self.menu_items)
            self.audio.play("menu_move")
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            choice = self.menu_items[self.menu_index]
            if choice == "Play Game":
                self.reset_game()
                self.state = "playing"
                self.audio.play("start")
            elif choice == "About":
                self.state = "about"
                self.audio.play("menu_select")
            elif choice == "Help":
                self.state = "help"
                self.audio.play("menu_select")
            elif choice == "Exit":
                self.quit_game()

    def handle_game_input(self, event):
        if event.key == pygame.K_ESCAPE:
            self.state = "menu"
            self.audio.play("menu_select")
            return

        if event.key in (pygame.K_UP, pygame.K_w) and self.direction != (0, 1):
            self.next_direction = (0, -1)
        elif event.key in (pygame.K_DOWN, pygame.K_s) and self.direction != (0, -1):
            self.next_direction = (0, 1)
        elif event.key in (pygame.K_LEFT, pygame.K_a) and self.direction != (1, 0):
            self.next_direction = (-1, 0)
        elif event.key in (pygame.K_RIGHT, pygame.K_d) and self.direction != (-1, 0):
            self.next_direction = (1, 0)

    def update(self):
        if self.state != "playing":
            return

        self.move_timer += 1
        if self.move_timer < self.move_delay_frames:
            return
        self.move_timer = 0

        self.direction = self.next_direction
        head_x, head_y = self.snake[0]
        dx, dy = self.direction
        new_head = (head_x + dx, head_y + dy)

        if (
            new_head[0] < 0
            or new_head[0] >= GRID_W
            or new_head[1] < 0
            or new_head[1] >= GRID_H
            or new_head in self.snake[:-1]
        ):
            self.state = "game_over"
            self.audio.play("game_over")
            return

        self.snake.insert(0, new_head)

        if new_head == (self.food.x, self.food.y):
            self.score += 1
            self.food = self.spawn_food()
            self.audio.play("eat")
        else:
            self.snake.pop()

    def draw(self):
        self.screen.fill(FAMICOM_BG)

        if self.state == "menu":
            self.draw_menu()
        elif self.state == "playing":
            self.draw_game()
        elif self.state == "about":
            self.draw_about()
        elif self.state == "help":
            self.draw_help()
        elif self.state == "game_over":
            self.draw_game()
            self.draw_game_over()

    def draw_menu(self):
        self.draw_panel(60, 40, WIDTH - 120, HEIGHT - 80)

        title_surface = self.font_title.render(TITLE, True, FAMICOM_GOLD)
        subtitle_surface = self.font_medium.render(SUBTITLE, True, FAMICOM_LIGHT)

        self.screen.blit(
            title_surface,
            title_surface.get_rect(center=(WIDTH // 2, 90)),
        )
        self.screen.blit(
            subtitle_surface,
            subtitle_surface.get_rect(center=(WIDTH // 2, 125)),
        )

        for i, item in enumerate(self.menu_items):
            selected = i == self.menu_index
            color = FAMICOM_RED if selected else WHITE
            prefix = "> " if selected else "  "
            text = self.font_medium.render(prefix + item, True, color)
            self.screen.blit(
                text,
                text.get_rect(center=(WIDTH // 2, 190 + i * 38)),
            )

        footer = self.font_small.render("Famicom style • 600x400 • 60 FPS", True, FAMICOM_LIGHT)
        self.screen.blit(footer, footer.get_rect(center=(WIDTH // 2, HEIGHT - 55)))

    def draw_game(self):
        self.draw_checker_background()
        self.draw_border()
        self.draw_food()
        self.draw_snake()

        score_text = self.font_small.render(f"SCORE {self.score:03d}", True, WHITE)
        fps_text = self.font_small.render("60 FPS", True, FAMICOM_LIGHT)
        title_text = self.font_small.render("CAT'S SNAKE", True, FAMICOM_GOLD)

        self.screen.blit(score_text, (12, 10))
        self.screen.blit(title_text, (WIDTH // 2 - title_text.get_width() // 2, 10))
        self.screen.blit(fps_text, (WIDTH - fps_text.get_width() - 12, 10))

    def draw_about(self):
        self.draw_panel(50, 50, WIDTH - 100, HEIGHT - 100)
        lines = [
            "ABOUT",
            "",
            "Cat's Snake py port 0.1",
            "A retro snake game with a Famicom look.",
            "",
            "Python 3.14 compatible",
            "Window: 600x400",
            "Framerate: 60 FPS",
            "",
            "Press Enter, Space, or Esc to return",
        ]
        self.draw_centered_lines(lines, 90)

    def draw_help(self):
        self.draw_panel(50, 50, WIDTH - 100, HEIGHT - 100)
        lines = [
            "HELP",
            "",
            "Move: Arrow keys or WASD",
            "Start / Select: Enter or Space",
            "Back to menu: Esc",
            "",
            "Eat food to grow.",
            "Avoid walls and your own tail.",
            "",
            "Press Enter, Space, or Esc to return",
        ]
        self.draw_centered_lines(lines, 90)

    def draw_game_over(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        self.draw_panel(120, 120, WIDTH - 240, HEIGHT - 240)

        game_over_text = self.font_large.render("GAME OVER", True, FAMICOM_RED)
        score_text = self.font_medium.render(f"SCORE {self.score:03d}", True, WHITE)
        retry_text = self.font_small.render("Enter = Retry   Esc = Menu", True, FAMICOM_LIGHT)

        self.screen.blit(game_over_text, game_over_text.get_rect(center=(WIDTH // 2, 165)))
        self.screen.blit(score_text, score_text.get_rect(center=(WIDTH // 2, 205)))
        self.screen.blit(retry_text, retry_text.get_rect(center=(WIDTH // 2, 245)))

    def draw_centered_lines(self, lines, start_y):
        y = start_y
        for line in lines:
            if line == "":
                y += 16
                continue

            if line in ("ABOUT", "HELP"):
                surf = self.font_large.render(line, True, FAMICOM_GOLD)
            else:
                surf = self.font_small.render(line, True, WHITE)

            self.screen.blit(surf, surf.get_rect(center=(WIDTH // 2, y)))
            y += 26

    def draw_panel(self, x, y, w, h):
        pygame.draw.rect(self.screen, FAMICOM_PANEL, (x, y, w, h))
        pygame.draw.rect(self.screen, FAMICOM_LIGHT, (x, y, w, h), 4)
        pygame.draw.rect(self.screen, FAMICOM_DARK, (x + 6, y + 6, w - 12, h - 12), 2)

    def draw_checker_background(self):
        for gy in range(GRID_H):
            for gx in range(GRID_W):
                color = FAMICOM_BG if (gx + gy) % 2 == 0 else (36, 40, 60)
                pygame.draw.rect(
                    self.screen,
                    color,
                    (gx * CELL, gy * CELL, CELL, CELL),
                )

    def draw_border(self):
        pygame.draw.rect(self.screen, FAMICOM_LIGHT, (0, 0, WIDTH, HEIGHT), 4)

    def draw_snake(self):
        for i, (x, y) in enumerate(self.snake):
            px = x * CELL
            py = y * CELL
            color = FAMICOM_GOLD if i == 0 else FAMICOM_GREEN
            inner = FAMICOM_RED if i == 0 else FAMICOM_LIGHT

            pygame.draw.rect(self.screen, color, (px + 1, py + 1, CELL - 2, CELL - 2))
            pygame.draw.rect(self.screen, inner, (px + 5, py + 5, CELL - 10, CELL - 10))

            if i == 0:
                eye_color = BLACK
                pygame.draw.rect(self.screen, eye_color, (px + 5, py + 5, 3, 3))
                pygame.draw.rect(self.screen, eye_color, (px + CELL - 8, py + 5, 3, 3))

    def draw_food(self):
        px = self.food.x * CELL
        py = self.food.y * CELL
        pygame.draw.rect(self.screen, FAMICOM_RED, (px + 2, py + 2, CELL - 4, CELL - 4))
        pygame.draw.rect(self.screen, FAMICOM_GOLD, (px + 6, py + 6, CELL - 12, CELL - 12))

    def quit_game(self):
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    SnakeGame().run()
