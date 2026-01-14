#!/usr/bin/env python3
import time

def main():
	while True:
		# Do your background work here
		print("Hello from worker service...")
		time.sleep(5)

if __name__ == "__main__":
	main()