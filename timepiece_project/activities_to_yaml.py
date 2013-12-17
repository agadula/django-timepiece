input = './fixtures/activities-projects.txt'
output = './fixtures/activities-projects.yaml'


def is_activity(line):
    cond_1 = line[0].isdigit() and line[1] == '.' and line[2].isdigit()
    cond_2 = line[0] in ['A', 'C'] and line[1] == '.' and line[2].isdigit()
    cond_3 = line.startswith("IPA") or line.startswith("ENP")
    if cond_1 or cond_2 or cond_3:
        return True


def status_and_type2fixture():
    return """
- model: crm.attribute
  pk: 1
  fields:
    type: 'project-status'
    label: "Active"
    enable_timetracking: True

- model: crm.attribute
  pk: 2
  fields:
    type: 'project-type'
    label: "Standard type"
    enable_timetracking: True



"""

def activity2fixture(pk, name):
    result = '- model: crm.business\n'
    result+= '  pk: '+str(pk)+'\n'
    result+= '  fields:\n'
    result+= '    name: \'' + name + '\'\n'
    result+= '\n'
    return result


def project2fixture(pk, name, act_pk):
    result = '- model: crm.project\n'
    result+= '  pk: '+str(pk)+'\n'
    result+= '  fields:\n'
    result+= '    name: \'' + name + '\'\n'
    result+= '    business: '+str(act_pk)+'\n'
    result+= '    point_person : 1\n'
    result+= '    type: 2\n'
    result+= '    status: 1\n'
    result+= '\n'
    return result




with open(input) as f:
    activities = []
    lines = f.readlines()
    for line in lines:
        line = line.strip()
        if line == '' or line == "Administrative activities":
            continue
        if is_activity(line):
            line = " ".join(line.split()) # remove double spaces
            activities.append( { 'name': line, 'projects': [] } )
            if line.startswith("IPA") or line.startswith("ENP") or line.startswith("7.1 Operational Management and Support"):
                # these activities have no projects, thus a single project with the same name is created
                activities[-1]['projects'].append( line )
        else:
            activities[-1]['projects'].append( line )

#     for a in activities:
#         print a['name']
#         for p in a['projects']:
#             print '> '+p
#         print
#     print
#     print len(activities)

with open(output, "w") as f:
    act_id = 1
    prj_id = 1
    
    f.write( status_and_type2fixture() )
    
    for a in activities:
        f.write( activity2fixture(act_id, a["name"]) )
        for p in a["projects"]:
            f.write( project2fixture(prj_id, p, act_id) )
            prj_id+= 1
        f.write("\n\n")
        act_id+= 1
