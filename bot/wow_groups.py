from ortools.linear_solver import pywraplp
import random
import math
import numpy as np
import logging
import hjson

DPS='dps'
HEAL='heal'
TANK='tank'

"""
Returns the number of members able to perform a specific role,
independently of their commitment to it
"""
def how_many_members_for_role(members, role):
    nbr = 0
    for member in members:
        if member[2] == role:
            nbr += 1
    return nbr


"""
Create a line of the member list (see the function below)
"""
def build_line(player, role, current_member):
    line = []
    line.append(player['name']+"_"+role)
    line.append(player['name'])
    line.append(role)
    line.append(player['wishes'][role])
    line.append(current_member)
    return line


"""
Replace the input dictionnary of players 
by a list where each tuple member/role is a separate item
"""
def build_members(players):
    members = []
    current_member = 0

    for player in players:
        for role in [HEAL, TANK, DPS]:
            if role in player['wishes'] and player['wishes'][role] > 0:
                members.append(build_line(player, role, current_member))
        current_member += 1

    random.shuffle(members)
    return members


"""
Format the output solution from the x[i,j] items matrix
to a readable dictionnary
"""
def get_dict_from_solution(data, x):
    result = []
    for j in data['bins']:
        group_commitment = 0
        group = {}
        group['id'] = j+1
        group['members'] = []
        for i in data['items']:
            if x[i, j].solution_value() > 0:
                member = {}
                member['name'] = data['names'][i]
                member['role'] = data['roles'][i]
                member['commitment'] = math.floor(data['values'][i])
                group_commitment += member['commitment']
                group['members'].append(member)
        group['commitment'] = group_commitment
        result.append(group)
    return result


"""
inputs all data in the Google OR algorithm
and create the internal object we manipulate
The number of expected groups is roughly computed,
and will be refined if no solution is found
"""
def create_data_model(players, group_size):
    members = build_members(players)

    nbr_groups = min(math.floor(
        len(players)/group_size),
        how_many_members_for_role(members, HEAL),
        how_many_members_for_role(members, TANK),
        math.floor(how_many_members_for_role(members, DPS)/(group_size-2)))

    data = {}
    data['id'] = [x[0] for x in members]
    data['names'] = [x[1] for x in members]
    data['roles'] = [x[2] for x in members]
    data['values'] = [x[3] for x in members]
    data['players'] = [x[4] for x in members]
    data['items'] = list(range(len(members)))
    data['num_items'] = len(members)
    data['bin_capacities'] = np.full(shape=nbr_groups, fill_value=group_size, dtype=np.int)
    data['members'] = members
    data['bins'] = list(range(len(data['bin_capacities'])))
    return data


"""
Reduce the number of expected groups in the solution
it is used before asking for another computing
"""
def reduce_bin_capacity(data, group_size):
    nbr_groups = len(data['bin_capacities']) - 1
    if nbr_groups < 1:
        nbr_groups = 1
    data['bin_capacities'] = np.full(shape=nbr_groups, fill_value=group_size, dtype=np.int)
    data['bins'] = list(range(len(data['bin_capacities'])))
    return data


"""
Get the current number of groups expected in the solution
"""
def get_bin_capacity(data):
    return len(data['bin_capacities'])


"""
Returns a reduction of the internal matrix of items
to those concerning a single player, accross all groups
"""
def get_x_for_single_player(player, x, data):
    p = {}
    for i in data['items']:
        same_player = (data['players'][i] == player)
        if not same_player:
            continue
        for j in data['bins']:
            p[(i, j)] = x[(i, j)]
    return p


"""
Returns a reduction of the internal matrix of items
to those concerning a single role, accross all groups and players
"""
def get_x_for_single_role(role, current_bin, x, data):
    r = {}
    for i in data['items']:
        same_role = (data['roles'][i] == role)
        if not same_role:
            continue
        r[(i, current_bin)] = x[(i, current_bin)]
    return r


"""
Returns a reduction of the internal matrix of items
to those concerning a single item, accross all groups
"""
def get_x_per_item(solver, data):
    # x[i, j] = 1 if item i is packed in bin j.
    # p[i, j] = 1 if player from item i is packed in bin j.
    x = {}
    for i in data['items']:
        for j in data['bins']:
            x[(i, j)] = solver.IntVar(0, 1, 'x_%i_%i' % (i, j))
    return x


"""
Defines all contrains applied to the algorithm.

Those constraints must be applied to lists of x[i, j] items
where i is the item position in our original list, 
and j is the group (or bin in the algorithm's language).

Each x[i,j] item can have 2 states, 0 or 1. 
0 means it in not in this position, 1 means it is.

Those constraints are setup here, but will only be computed 
when the algorithm will need to check if each solution  it has matches 
our requirements. So you can't test the value here, just provide acceptable values.

For example, all x[i,j] items representing a single player 
(one item per role * number of groups) can only have a sum of 1 in the final solution,
to ensure the player has been selected only once in one role.
"""
def set_constraints(solver, data, x):
    # Each player can be picked only once in a single role.
    for i in data['items']:
        p = get_x_for_single_player(data['players'][i], x, data)
        solver.Add( sum(p[k] for k in p ) <= 1 ,'player_only_once')

    # No more than five people for each group
    for j in data['bins']:
        solver.Add(
            sum(x[(i, j)]
                for i in data['items']) <= data['bin_capacities'][j],'5_players')

    # 1 heal.
    for j in data['bins']:
        r = get_x_for_single_role(HEAL, j, x, data)
        solver.Add( sum(r[k] for k in r ) == 1 ,'only_one_heal')

    # 1 tank.
    for j in data['bins']:
        r = get_x_for_single_role(TANK, j, x, data)
        solver.Add( sum(r[k] for k in r ) == 1 ,'only_one_tank')


"""
Algorithm's objective will be to maximize player's commitment to their role,
represented by the value
"""
def set_objectives(solver, data, x):
    objective = solver.Objective()
    for i in data['items']:
        for j in data['bins']:
            objective.SetCoefficient(x[(i, j)], data['values'][i])
    objective.SetMaximization()


"""
Compute the group solution from the incoming list of dictionaries
"""
def get_groups(players, group_size = 5):
    data = create_data_model(players,group_size)
    while True:

        # Create the mip solver with the SCIP backend.
        solver = pywraplp.Solver.CreateSolver('SCIP')

        # Variables
        x = get_x_per_item(solver, data)

        # Constraints
        set_constraints(solver, data, x)

        # Objective
        set_objectives(solver, data, x)

        # Solve
        status = solver.Solve()

        # Check solution
        if status == pywraplp.Solver.OPTIMAL:
            return get_dict_from_solution(data, x)
        elif get_bin_capacity(data) <= 1:
            return {}
        else:
            data = reduce_bin_capacity(data, group_size)


"""
main function, used for testing or manual execution
"""
def main():
    players = []
    with open('../test/players.json') as json_file:
        players = hjson.load(json_file)
        
    solution = get_groups(players,5)
    json_object = hjson.dumpsJSON(solution, indent = 4)
    print(json_object)

if __name__ == '__main__':
    main()