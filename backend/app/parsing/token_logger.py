class GlobalTokenLogger:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.input_chars = 0
        self.output_chars = 0
        self.requests = 0

    def log(self, usage, input_text: str = "", output_text: str = ""):
        if not usage:
            return
        self.requests += 1
        self.input_tokens += getattr(usage, 'prompt_tokens', 0)
        self.output_tokens += getattr(usage, 'completion_tokens', 0)
        self.input_chars += len(input_text)
        self.output_chars += len(output_text)

    def summary(self):
        total_tokens = self.input_tokens + self.output_tokens
        cost = (self.input_tokens / 1_000_000) * 0.150 + (self.output_tokens / 1_000_000) * 0.600

        print("\n" + "="*50)
        print("                 LLM TELEMETRY")
        print("="*50)
        print(f"Model used:        gpt-4o-mini")
        print(f"Total Requests:    {self.requests}")
        print(f"Input Tokens:      {self.input_tokens:,}")
        print(f"Output Tokens:     {self.output_tokens:,}")
        print(f"Total Tokens:      {total_tokens:,}")
        print(f"Input Characters:  {self.input_chars:,}")
        print(f"Output Characters: {self.output_chars:,}")
        print("-" * 50)
        print(f"Estimated Cost:    ${cost:.6f}")
        print("="*50 + "\n")

    def reset(self):
        self.__init__()

# Global instance to be used across scripts
telemetry = GlobalTokenLogger()
