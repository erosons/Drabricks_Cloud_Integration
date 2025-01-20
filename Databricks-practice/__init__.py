def solution(T):
    # Sort the tasks in ascending order
    T.sort()
    
    total_waiting_time = 0
    current_time = 0
    
    # Compute the total waiting time
    for time in T:
        current_time += time  # Time spent making the current item
        total_waiting_time += current_time  # Add to total waiting time
        total_waiting_time %= 10**9  # Take modulo to avoid overflow
    
    return total_waiting_time

# Test cases
print(solution([3, 1, 2]))  # Output: 13
# print(solution([1, 2, 3, 4]))  # Output: 25
# print(solution([7, 7, 7]))  # Output: 60
# print(solution([10000]))  # Output: 10000
