import React, {useEffect, useState} from 'react';
import { StyleSheet, Text, View, ScrollView, TextInput, Button, FlatList } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

const SPORTS = [
  { id: 'nfl', label: 'NFL' },
  { id: 'ncaaf', label: 'College Football' },
  { id: 'nba', label: 'NBA' },
  { id: 'ncaam', label: "Men's College BB" },
  { id: 'ncaaw', label: "Women's College BB" },
];

const buildDate = (dayOffset = 0) => {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + dayOffset);
  return d.toISOString().slice(0, 10);
};

export default function App() {
  const [selectedSport, setSelectedSport] = useState(null);
  const [scores, setScores] = useState({});
  const [loading, setLoading] = useState(true);
  const [chat, setChat] = useState([{from:'bot', text:'Ask me for picks!'}]);
  const [msg, setMsg] = useState('');

  // Initialize selected sport on mount
  useEffect(() => {
    const initializeSport = async () => {
      try {
        // Try to get sports summary to find sport with most games
        const res = await fetch('http://localhost:5000/api/sports-summary');
        if (res.ok) {
          const data = await res.json();
          const sportsList = data.sports || [];

          // Find sport with most games
          const sportWithMostGames = sportsList.find(s => s.game_count > 0);
          if (sportWithMostGames) {
            const sport = SPORTS.find(s => s.id === sportWithMostGames.sport);
            if (sport) {
              setSelectedSport(sport);
              await AsyncStorage.setItem('lastBrowsedSport', sport.id);
              setLoading(false);
              return;
            }
          }
        }
      } catch (err) {
        // Silently fail and fall back to localStorage
      }

      // Fall back to last browsed sport or first sport
      try {
        const lastSport = await AsyncStorage.getItem('lastBrowsedSport');
        const sport = lastSport ? SPORTS.find(s => s.id === lastSport) : null;
        setSelectedSport(sport || SPORTS[0]);
      } catch (err) {
        setSelectedSport(SPORTS[0]);
      }
      setLoading(false);
    };

    initializeSport();
  }, []);

  // Save sport selection to AsyncStorage whenever it changes
  useEffect(() => {
    if (selectedSport) {
      AsyncStorage.setItem('lastBrowsedSport', selectedSport.id);
    }
  }, [selectedSport]);

  // Fetch scores for selected sport
  useEffect(() => {
    if (!selectedSport) return;

    const fetchScores = async () => {
      try {
        const date = buildDate(0);
        const res = await fetch(`http://localhost:5000/api/scoreboard?sport=${selectedSport.id}&date=${date}`);
        if (res.ok) {
          const data = await res.json();
          const events = data.scoreboard?.events || [];
          const gameCount = events.length;
          setScores(prev => ({
            ...prev,
            [selectedSport.label]: gameCount
          }));
        }
      } catch (err) {
        setScores(prev => ({
          ...prev,
          [selectedSport.label]: 0
        }));
      }
    };

    fetchScores();
  }, [selectedSport]);

  const send = () => {
    if(!msg) return;
    setChat([...chat, {from:'user', text:msg}, {from:'bot', text:'Got: '+msg}]);
    setMsg('');
  };

  const handleSelectSport = (sport) => {
    setSelectedSport(sport);
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Your Edge in Every Play</Text>
          <Text style={styles.subtitle}>AI-Powered Sports Picks · Live Updates</Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.h2}>📊 Live Scoreboard</Text>
        <ScrollView horizontal style={styles.sportTabs}>
          {SPORTS.map(sport => (
            <Button
              key={sport.id}
              title={sport.label}
              onPress={() => handleSelectSport(sport)}
              color={selectedSport?.id === sport.id ? '#0f766e' : '#64748b'}
            />
          ))}
        </ScrollView>
        {loading ? (
          <Text>Loading...</Text>
        ) : selectedSport ? (
          <View>
            <Text style={styles.sportLabel}>{selectedSport.label}</Text>
            <Text style={styles.gameCount}>
              {scores[selectedSport.label] || 0} games today
            </Text>
          </View>
        ) : null}
      </View>

      <View style={styles.card}>
        <Text style={styles.h2}>💬 AI Assistant</Text>
        {chat.map((c, i) => (
          <View key={i} style={[styles.chatBubble, c.from === 'user' ? styles.user : styles.bot]}>
            <Text>{c.text}</Text>
          </View>
        ))}
        <View style={{flexDirection:'row', marginTop:8}}>
          <TextInput
            value={msg}
            onChangeText={setMsg}
            style={styles.input}
            placeholder="Ask for picks..."
          />
          <Button title='Send' onPress={send} />
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container:{flex:1,backgroundColor:'#f7fafc',padding:12},
  header:{flexDirection:'column',marginBottom:12},
  title:{fontSize:18,fontWeight:'700',marginBottom:4},
  subtitle:{color:'#64748b',fontSize:13},
  card:{backgroundColor:'#fff',padding:12,borderRadius:8,marginBottom:12},
  h2:{fontSize:16,fontWeight:'700',marginBottom:12},
  sportTabs:{marginBottom:12,marginHorizontal:-12,paddingHorizontal:12},
  sportLabel:{fontSize:14,fontWeight:'600',marginBottom:6},
  gameCount:{fontSize:16,fontWeight:'700',color:'#0f766e'},
  chatBubble:{padding:8,borderRadius:8,marginTop:6,maxWidth:'80%'},
  user:{backgroundColor:'#e6fffb',alignSelf:'flex-end'},
  bot:{backgroundColor:'#f1f5f9',alignSelf:'flex-start'},
  input:{flex:1,borderWidth:1,borderColor:'#e2e8f0',borderRadius:6,padding:8,marginRight:8}
});
