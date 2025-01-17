# This file will attempt to make a graph out of the municipalities in Mexico using the municipalities.json file

import json
import csv
import heapq
import math
import folium
import functools

MAX_EDGES = 10 # max number of connected municipalities
MAX_DISTANCE = 100 # miles (all distances are in miles unless otherwise specified)


class MunicipalityEdge:
	def __init__(self, fromMuniCode, toMuniCode, distance=None):
		self.fromMuniCode = fromMuniCode
		self.toMuniCode = toMuniCode
		self.distance = distance

	def __str__(self):
		return str(self.fromMuniCode) + " -> " + str(self.toMuniCode) + ", distance: " + str(self.distance)

	def __lt__(self, other):
		return self.distance < other.distance

	def setEdgeDistance(self, distance):
		if not self.distance:
			self.distance = distance


class Municipality:
	def __init__(self, name, state, code, lat, lon, hasSupercharger=False, edges=None):
		self.name = name
		self.state = state
		self.code = code
		self.lat = lat
		self.lon = lon
		self.hasSupercharger = hasSupercharger
		self._neighbors = set([edge["toMuniCode"] for edge in edges]) if edges else set([])
		self.edges = [MunicipalityEdge(
			edge["fromMuniCode"], 
			edge["toMuniCode"], 
			edge["distance"]) for edge in edges] if edges else []
	
	def __str__(self):
		return self.name + ", " + self.state + ", " + self.code + ", " + str(self.hasSupercharger)

	# OUTDATED, now directly adding edges to the municipality in v2
	def addEdge(self, edge: MunicipalityEdge):
		# See if the edge.value is greater than the smallest edge in the heap
		# If it is, then pop the smallest edge and push the new edge
		# Otherwise, do nothing
		isValidDistance = edge.distance < MAX_DISTANCE or ((edge.fromMuniCode.startswith('09') or edge.toMuniCode.startswith('09')) and edge.distance < 2 * MAX_DISTANCE)
		if isValidDistance and (len(self.edges) < MAX_EDGES or edge.distance > self.edges[0].distance):
			heapq.heappush(self.edges, edge)
			if len(self.edges) > MAX_EDGES:
				heapq.heappop(self.edges)


def municipalityDictSerializer(obj):
	if isinstance(obj, Municipality):
		dictionary = obj.__dict__
		del dictionary['_neighbors']
		return dictionary
	if isinstance(obj, MunicipalityEdge):
		return obj.__dict__
	raise TypeError("Type not serializable")


def cleanMunicipalities():
	print("Opening municipalities.json")
	municipalities = None

	with open("municipalities.json") as file:
		# Remove the geo_shape keys
		municipalities = json.load(file)
		for municipality in municipalities:
			del municipality['geo_shape']

	# Save the municipalities as a json file
	with open('cleanMunicipalities.json', 'w') as file:
		json.dump(municipalities, file)

	print("Municipalities read in, cleaned, and saved.")


def loadCleanMunicipalities():
	with open('cleanMunicipalities.json') as file:
		return json.load(file)


def loadCleanSuperchargers():
	# Read in the CSV so that it is a dictionary
	with open('cleanSuperchargers.csv') as file:
		reader = csv.DictReader(file)
		return [row for row in reader]


def saveMunicipalityWithSuperchargers():
	# For each supercharger, determine if its city is in the municipalities.json file
	municipalities = loadCleanMunicipalities()
	superchargers = loadCleanSuperchargers()

	print("Total municipalities:", len(municipalities))

	# Create a dictionary of municipality names to Municipality objects
	nameToMunicipality: dict[str, list[Municipality]] = {}

	# Iterate over the municipalities and add them to the dictionary
	for municipality in municipalities:
		dictLookup = municipality['sta_name'][0]+"_"+municipality['mun_name'][0]
		if dictLookup in nameToMunicipality:
			# Append it to the list of municipalities with the same name
			nameToMunicipality[dictLookup].append(Municipality(
				municipality['mun_name'][0], 
				municipality['sta_name'][0], 
				municipality['mun_code'][0], 
				municipality['geo_point_2d']['lat'], 
				municipality['geo_point_2d']['lon']))
		else: nameToMunicipality[dictLookup] = [Municipality(
			municipality['mun_name'][0], 
			municipality['sta_name'][0], 
			municipality['mun_code'][0], 
			municipality['geo_point_2d']['lat'],
			municipality['geo_point_2d']['lon'])]

	# Iterate over the superchargers and see how many of their cities are in the municipalities
	for supercharger in superchargers:
		escapedMunicipality = supercharger['State']+"_"+supercharger['Municipality']
		decodedMunicipality = escapedMunicipality.encode('utf-8').decode('unicode-escape')
		if decodedMunicipality not in nameToMunicipality:
			print("Bad supercharger location: ", decodedMunicipality)
			continue
		muniArr = nameToMunicipality[decodedMunicipality]
		for municipality in muniArr:
			municipality.hasSupercharger = True

	totalWithSuperchargers = 0
	for municipality, objArr in nameToMunicipality.items():
		for obj in objArr:
			if obj.hasSupercharger: totalWithSuperchargers += 1

	# Should be 32 total
	print("Total with superchargers: ", totalWithSuperchargers)
	
	print("Total municipality names (does not include duplicates):", len(nameToMunicipality.items()))
	codeToMunicipality = {}
	for muniArr in nameToMunicipality.values():
		for municipality in muniArr:
			codeToMunicipality[municipality.code] = municipality
	print("Total codes:", len(codeToMunicipality.items()))

	# Write the municipalities (with codes) to a JSON file
	with open('cleanMunicipalitiesWithSuperchargers.json', 'w') as file:
		json.dump(codeToMunicipality, file, default=municipalityDictSerializer)


def getMunicipalityCodeToSuperchargerStatus():
	# Read each code:Municipality object from the JSON file
	with open('cleanMunicipalitiesWithSuperchargers.json') as file:
		obj = json.load(file)
		# Map each value to a Municipality object
		return {code: Municipality(**value) for code, value in obj.items()}


@functools.lru_cache(maxsize=None)
def getDistanceBetweenMunicipalities(muni1, muni2):
	# Use the Haversine formula to get the distance between two points
	lat1, lon1 = muni1.lat, muni1.lon
	lat2, lon2 = muni2.lat, muni2.lon

	R = 6371 # meters
	dLat = math.radians(lat2 - lat1)
	dLon = math.radians(lon2 - lon1)
	lat1 = math.radians(lat1)
	lat2 = math.radians(lat2)

	a = math.sin(dLat/2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dLon/2) ** 2
	c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
	distance = R * c

	# Convert to miles
	return distance / 1.609


def addEdgesToMunicipalities():
	# Read in the municipalities with the supercharger status
	codeToMunicipality = getMunicipalityCodeToSuperchargerStatus()
	codeToMunicipalityValues : list[Municipality] = list(codeToMunicipality.values())
	for i in range(len(codeToMunicipalityValues)):
		closenessHeap = []
		muni1 = codeToMunicipalityValues[i]
		# Essentially gather the closest MAX_EDGES edges to each municipality
		for j in range(len(codeToMunicipalityValues)):
			if i == j: continue
			muni2 = codeToMunicipalityValues[j]
			if muni2.code in muni1._neighbors: continue
			distance = getDistanceBetweenMunicipalities(muni1, muni2)
			heapq.heappush(closenessHeap, (distance, muni2))

		# Add the closest MAX_EDGES edges to each municipality
		for j in range(MAX_EDGES):
			if not closenessHeap: break
			distance, muni2 = heapq.heappop(closenessHeap)
			# Use MAX_DISTANCE / powers of 2 and 3 to limit the number of nodes with a BUNCH of edges.
			if (j < 3 and distance > (MAX_DISTANCE/(2**j))) or (j >= 3 and distance > (MAX_DISTANCE/(3**j))): break
			# Construct the edges
			edgeToMuni2 = MunicipalityEdge(muni1.code, muni2.code, distance)
			edgeToMuni1 = MunicipalityEdge(muni2.code, muni1.code, distance)
			# Add the edge to the municipalities, remembering that it has already been visited.
			muni1.edges.append(edgeToMuni2)
			muni1._neighbors.add(muni2.code)
			muni2.edges.append(edgeToMuni1)
			muni2._neighbors.add(muni1.code)

	# Save to file allMunicipalitiesGraph.json (one level up and in a folder called graphs)
	with open('../graphs/allMunicipalitiesGraph.json', 'w') as file:
		json.dump(codeToMunicipality, file, default=municipalityDictSerializer)

	return codeToMunicipality


def loadMunicipalitiesWithEdges():
	with open('../graphs/allMunicipalitiesGraph.json') as file:
		obj = json.load(file)
		return {code: Municipality(**value) for code, value in obj.items()}


def testAndSaveToMap(codeToMuni, outputFile="mexicoMap.html"):
	totalEdges = 0
	for muni in codeToMuni.values():
		totalEdges += len(muni.edges)
	print("Total out edges:", totalEdges)

	# Latitude and Longitude of Mexico City (example)
	latitude, longitude = 19.4326, -99.1332

	# Create a map centered around Mexico
	mexico_map = folium.Map(location=[latitude, longitude], zoom_start=15)

	for muni in codeToMuni.values():
		# Add a marker to the map
		folium.Marker([muni.lat, muni.lon], popup=muni.name).add_to(mexico_map)

		# Add a line between the municipality and its neighbors
		for edge in muni.edges:
			# Get the neighbor
			neighbor = codeToMuni[edge.toMuniCode]
			# Add a line between the two municipalities
			folium.PolyLine([[muni.lat, muni.lon], [neighbor.lat, neighbor.lon]], color="red", weight=1, opacity=0.5).add_to(mexico_map)

	# Save the map to an HTML file
	mexico_map.save(outputFile)
	print("Saved interactive map")


def main():
	print("Beginning data processing...\n")

	# Clean the municipalities data (raw), already performed and original file deleted.
	# cleanMuncipalities()

	# Combine the two datasets to mark which muncipalities have the superchargers in them
	saveMunicipalityWithSuperchargers()

	# Next, add edges between municipalities
	codeToMuni = addEdgesToMunicipalities()

	# Finally, make and save the map of these municipalities
	testAndSaveToMap(codeToMuni)
	print("Data processing has succeeded.")

if __name__ == '__main__':
	main()
