def solution(T):
    total_waiting_time = 0
    current_time = 0
    
    for time in sorted(T):
        current_time += time
        total_waiting_time += current_time
    
    return total_waiting_time % 10**9

# Example usage:
print(solution([3, 1, 2]))  # Expected output: 13
print(solution([1, 2, 3, 4]))  # Expected output: 25
print(solution([7, 7, 7]))  # Expected output: 60
print(solution([10000]))  # Expected output: 10000
print(solution([10, 20, 42]))  # Additional test case
