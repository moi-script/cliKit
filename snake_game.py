import pygame
import random
import sys

# Initialize Pygame
pygame.init()

# --- Constants ---
SCREEN_WIDTH = 600
SCREEN_HEIGHT = 400
GRID_SIZE = 20
GRID_WIDTH = SCREEN_WIDTH // GRID_SIZE
GRID_HEIGHT = SCREEN_HEIGHT // GRID_SIZE

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
ORANGE = (255, 165, 0)

# Directions
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)

# Game Speed
INITIAL_SPEED = 10 # frames per second

# --- Game Setup ---
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Snake Game")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 36)

class Snake:
    def __init__(self):
        self.length = 1
        self.positions = [((SCREEN_WIDTH // 2), (SCREEN_HEIGHT // 2))]
        self.direction = random.choice([UP, DOWN, LEFT, RIGHT])
        self.color = GREEN
        self.score = 0

    def get_head_position(self):
        return self.positions[0]

    def turn(self, point):
        # Prevent turning 180 degrees instantly
        if self.length > 1 and \
           (point[0] * -1, point[1] * -1) == self.direction:
            return
        self.direction = point

    def move(self):
        cur = self.get_head_position()
        x, y = self.direction
        new = (((cur[0] + (x * GRID_SIZE)) % SCREEN_WIDTH),
               ((cur[1] + (y * GRID_SIZE)) % SCREEN_HEIGHT))
        
        # Check for self-collision before updating positions
        if len(self.positions) > 2 and new in self.positions[2:]:
            return True # Game Over
        
        self.positions.insert(0, new)
        if len(self.positions) > self.length:
            self.positions.pop()
        
        return False # Not Game Over

    def eat(self):
        self.length += 1
        self.score += 10

    def draw(self, surface):
        for p in self.positions:
            pygame.draw.rect(surface, self.color, (p[0], p[1], GRID_SIZE, GRID_SIZE))

    def reset(self):
        self.length = 1
        self.positions = [((SCREEN_WIDTH // 2), (SCREEN_HEIGHT // 2))]
        self.direction = random.choice([UP, DOWN, LEFT, RIGHT])
        self.score = 0

class Food:
    def __init__(self, snake_positions, walls):
        self.position = (0, 0)
        self.color = RED
        self.randomize_position(snake_positions, walls)

    def randomize_position(self, snake_positions, walls):
        while True:
            x = random.randint(0, GRID_WIDTH - 1) * GRID_SIZE
            y = random.randint(0, GRID_HEIGHT - 1) * GRID_SIZE
            new_pos = (x, y)
            
            # Ensure food does not spawn on snake or wall
            if new_pos not in snake_positions and new_pos not in [w.position for w in walls]:
                self.position = new_pos
                break

    def draw(self, surface):
        pygame.draw.rect(surface, self.color, (self.position[0], self.position[1], GRID_SIZE, GRID_SIZE))

class Wall:
    def __init__(self, x, y):
        self.position = (x, y)
        self.color = ORANGE

    def draw(self, surface):
        pygame.draw.rect(surface, self.color, (self.position[0], self.position[1], GRID_SIZE, GRID_SIZE))

def create_walls():
    walls = []
    # Example walls: border
    for x in range(0, SCREEN_WIDTH, GRID_SIZE):
        walls.append(Wall(x, 0)) # Top border
        walls.append(Wall(x, SCREEN_HEIGHT - GRID_SIZE)) # Bottom border
    for y in range(GRID_SIZE, SCREEN_HEIGHT - GRID_SIZE, GRID_SIZE):
        walls.append(Wall(0, y)) # Left border
        walls.append(Wall(SCREEN_WIDTH - GRID_SIZE, y)) # Right border
    
    # You can add more complex wall patterns here
    # Example: A central block
    # for i in range(5):
    #     walls.append(Wall(SCREEN_WIDTH // 2 - GRID_SIZE * 2 + i * GRID_SIZE, SCREEN_HEIGHT // 2))
    
    return walls

def show_game_over_screen(score):
    screen.fill(BLACK)
    game_over_text = font.render("GAME OVER!", True, RED)
    score_text = font.render(f"Score: {score}", True, WHITE)
    restart_text = font.render("Press R to Restart or Q to Quit", True, WHITE)

    screen.blit(game_over_text, (SCREEN_WIDTH // 2 - game_over_text.get_width() // 2, SCREEN_HEIGHT // 2 - 50))
    screen.blit(score_text, (SCREEN_WIDTH // 2 - score_text.get_width() // 2, SCREEN_HEIGHT // 2))
    screen.blit(restart_text, (SCREEN_WIDTH // 2 - restart_text.get_width() // 2, SCREEN_HEIGHT // 2 + 50))
    pygame.display.flip()

    waiting_for_input = True
    while waiting_for_input:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    waiting_for_input = False
                    return True # Restart game
                if event.key == pygame.K_q:
                    pygame.quit()
                    sys.exit()
    return False # Should not reach here if quitting or restarting

def main_game_loop():
    snake = Snake()
    walls = create_walls()
    food = Food(snake.positions, walls)
    
    game_over = False

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    snake.turn(UP)
                elif event.key == pygame.K_DOWN:
                    snake.turn(DOWN)
                elif event.key == pygame.K_LEFT:
                    snake.turn(LEFT)
                elif event.key == pygame.K_RIGHT:
                    snake.turn(RIGHT)

        if not game_over:
            # Snake movement and collision detection
            if snake.move(): # Returns True if self-collision occurs
                game_over = True

            head_pos = snake.get_head_position()

            # Wall collision
            for wall in walls:
                if head_pos == wall.position:
                    game_over = True
                    break
            
            # Food collision
            if head_pos == food.position:
                snake.eat()
                food.randomize_position(snake.positions, walls)

            # Drawing
            screen.fill(BLACK) # Clear screen
            snake.draw(screen)
            food.draw(screen)
            for wall in walls:
                wall.draw(screen)

            # Display score
            score_text = font.render(f"Score: {snake.score}", True, WHITE)
            screen.blit(score_text, (5, 5))

            pygame.display.flip() # Update the full display Surface
            clock.tick(INITIAL_SPEED) # Control game speed
        else:
            if show_game_over_screen(snake.score):
                snake.reset()
                walls = create_walls() # Recreate walls in case they change
                food.randomize_position(snake.positions, walls)
                game_over = False

if __name__ == "__main__":
    main_game_loop()